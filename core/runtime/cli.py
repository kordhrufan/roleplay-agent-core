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
from core.character.models import (
    DRAFT_ID,
    CharacterDraftView,
    CharacterError,
    CharacterProposal,
    ConceptVersion,
    EffectiveComposition,
    ProposalView,
    composition_record,
    concept_record,
    concept_summary,
    decision_record,
    draft_summary,
    draft_view_record,
    proposal_record,
    staff_response_record,
)
from core.memory.narrative import (
    ExternalPost,
    HumanSeed,
    LoadedNarrativeTopic,
    NarrativeDraftView,
    NarrativeError,
    NarrativePostView,
    narrative_draft_summary,
    post_summary,
    publication_summary,
    seed_summary,
    topic_summary,
)
from core.review.models import ReviewStatus
from core.runtime.assimilation import (
    AssimilationCandidate,
    AssimilationDecision,
    AssimilationError,
    DossierSection,
    _candidate_record,
    _source_declarations,
    _SourceDeclaration,
    add_candidate,
    close_assimilation,
    close_expansion,
    record_candidate_decision,
)
from core.runtime.character import (
    add_proposal,
    citation_lines,
    create_draft,
    draft_reference_lines,
    get_concept,
    get_draft,
    get_effective_composition,
    get_proposal,
    import_concept,
    list_concepts,
    list_drafts,
    list_proposals,
    proposal_blocks,
    record_proposal_decision,
    record_staff_response,
    response_block,
    sheet_block,
)
from core.runtime.instance import (
    ApprovedCorpusEntry,
    InstanceError,
    LoadedInstance,
    approved_corpus,
    closed_corpus_of,
    create_instance,
    get_approved_candidate,
    load_instance,
    update_instance,
    update_instance_instructions,
)
from core.runtime.narrative import (
    confirm_narrative_publication,
    create_narrative_draft,
    create_topic,
    get_narrative_draft,
    get_post,
    get_seed,
    get_topic,
    import_human_seed,
    list_narrative_drafts,
    list_posts,
    list_seeds,
    list_topics,
    record_external_post,
)
from core.runtime.persistence import PersistenceError, load_strict_json
from core.runtime.workspace import (
    CORPUS_STATE,
    LoadedWorkspace,
    WorkspaceError,
    create_expansion_workspace,
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
    except (WorkspaceError, AssimilationError, PersistenceError, InstanceError,
            CharacterError, NarrativeError) as exc:
        return _fail(args, exc.code, exc.reason)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core.runtime.cli",
        description="Prepara el workspace de asimilación de un foro y su instancia. No "
                    "publica nada.",
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    commands = parser.add_subparsers(dest="command", required=True, metavar="comando")

    assimilation = commands.add_parser("assimilation", help="workspace de asimilación")
    groups = assimilation.add_subparsers(dest="group", required=True, metavar="acción")

    init = groups.add_parser("init", help="importa un expediente listo a un workspace externo")
    init.add_argument("--dossier", required=True, type=Path, help="carpeta del expediente")
    _workspace_argument(init)
    init.set_defaults(handler=_assimilation_init, action_name="assimilation.init")

    extend = groups.add_parser(
        "extend", help="crea un workspace de ampliación de una instancia con un expediente "
                       "sucesor que solo añade fuentes")
    _instance_argument(extend)
    extend.add_argument("--dossier", required=True, type=Path,
                        help="carpeta del expediente sucesor")
    _workspace_argument(extend)
    extend.set_defaults(handler=_assimilation_extend, action_name="assimilation.extend")

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
    for name, status, help_text in (
        ("approve", ReviewStatus.APPROVED, "aprueba una versión; pide teclear una frase con un código en tu terminal; frena la automatización pero no autentica a la persona"),
        ("reject", ReviewStatus.REJECTED, "rechaza una versión; pide teclear una frase con un código en tu terminal; frena la automatización pero no autentica a la persona"),
    ):
        decide = candidate_actions.add_parser(name, help=help_text)
        _workspace_argument(decide)
        decide.add_argument("--candidate-id", required=True)
        decide.add_argument("--version", required=True, type=int)
        decide.set_defaults(handler=_candidate_decide, review_status=status,
                            action_name=f"assimilation.candidate.{name}")

    decision = groups.add_parser("decision", help="decisiones humanas registradas")
    decision_actions = decision.add_subparsers(dest="decision_action", required=True,
                                               metavar="acción")
    decision_list = decision_actions.add_parser("list", help="lista las decisiones")
    _workspace_argument(decision_list)
    decision_list.set_defaults(handler=_decision_list, action_name="assimilation.decision.list")

    close = groups.add_parser("close", help="cierra la asimilación; pide teclear una frase con un código en tu terminal; frena la automatización pero no autentica a la persona")
    _workspace_argument(close)
    close.set_defaults(handler=_assimilation_close, action_name="assimilation.close")

    instance = commands.add_parser("instance", help="instancia del foro generada desde un "
                                                    "workspace cerrado")
    instance_actions = instance.add_subparsers(dest="instance_action", required=True,
                                               metavar="acción")
    instance_init = instance_actions.add_parser("init", help="crea la instancia en una carpeta "
                                                              "externa")
    _workspace_argument(instance_init)
    instance_init.add_argument("--output", required=True, type=Path,
                               help="carpeta de la instancia")
    instance_init.add_argument("--instructions-version", type=int, choices=(1, 2), default=1,
                               help="versión de las instrucciones del agente (por defecto 1)")
    instance_init.set_defaults(handler=_instance_init, action_name="instance.init")
    instance_update = instance_actions.add_parser(
        "update", help="adopta el snapshot cerrado de un workspace de ampliación; pide teclear una "
                       "frase con un código (no autentica a la persona)")
    _instance_argument(instance_update)
    _workspace_argument(instance_update)
    instance_update.set_defaults(handler=_instance_update, action_name="instance.update")
    instructions = instance_actions.add_parser("instructions",
                                               help="instrucciones del agente en la instancia")
    instructions_actions = instructions.add_subparsers(dest="instructions_action", required=True,
                                                       metavar="acción")
    instructions_update = instructions_actions.add_parser(
        "update", help="pasa las instrucciones de la v1 a la v2; pide teclear una frase con un "
                       "código (no autentica a la persona)")
    _instance_argument(instructions_update)
    instructions_update.set_defaults(handler=_instance_instructions_update,
                                     action_name="instance.instructions.update")
    instance_status = instance_actions.add_parser("status", help="comprueba la integridad")
    _instance_argument(instance_status)
    instance_status.set_defaults(handler=_instance_status, action_name="instance.status")
    corpus = instance_actions.add_parser("corpus", help="consulta el corpus aprobado")
    corpus_actions = corpus.add_subparsers(dest="corpus_action", required=True, metavar="acción")
    corpus_list = corpus_actions.add_parser("list", help="lista las versiones vigentes aprobadas")
    _instance_argument(corpus_list)
    corpus_list.set_defaults(handler=_instance_corpus_list, action_name="instance.corpus.list")
    corpus_show = corpus_actions.add_parser("show", help="muestra una versión aprobada")
    _instance_argument(corpus_show)
    corpus_show.add_argument("--candidate-id", required=True)
    corpus_show.add_argument("--version", required=True, type=_positive_int)
    corpus_show.set_defaults(handler=_instance_corpus_show, action_name="instance.corpus.show")
    corpus_history = corpus_actions.add_parser("history", help="cadena de snapshots cerrados")
    _instance_argument(corpus_history)
    corpus_history.set_defaults(handler=_instance_corpus_history,
                                action_name="instance.corpus.history")

    character = commands.add_parser("character", help="personajes de la instancia")
    character_groups = character.add_subparsers(dest="character_group", required=True,
                                                metavar="grupo")
    concept = character_groups.add_parser("concept", help="concepto aportado por la persona")
    concept_actions = concept.add_subparsers(dest="concept_action", required=True,
                                             metavar="acción")
    concept_import = concept_actions.add_parser(
        "import", help="declara un archivo como tu concepto; pide teclear una frase con un "
                       "código en tu terminal (frena la automatización, no autentica a la persona)")
    _instance_argument(concept_import)
    concept_import.add_argument("--character-id", required=True)
    concept_import.add_argument("--version", required=True, type=_positive_int)
    concept_import.add_argument("--input", required=True, type=Path,
                                help="archivo del concepto, fuera del checkout y de la instancia")
    concept_import.set_defaults(handler=_concept_import, action_name="character.concept.import")
    concept_list = concept_actions.add_parser("list", help="lista las versiones del concepto")
    _instance_argument(concept_list)
    concept_list.add_argument("--character-id", required=True)
    concept_list.set_defaults(handler=_concept_list, action_name="character.concept.list")
    concept_show = concept_actions.add_parser("show", help="muestra una versión del concepto")
    _instance_argument(concept_show)
    concept_show.add_argument("--character-id", required=True)
    concept_show.add_argument("--version", required=True, type=_positive_int)
    concept_show.set_defaults(handler=_concept_show, action_name="character.concept.show")
    effective = character_groups.add_parser("effective", help="composición efectiva del personaje")
    effective_actions = effective.add_subparsers(dest="effective_action", required=True,
                                                 metavar="acción")
    effective_show = effective_actions.add_parser(
        "show", help="muestra la composición efectiva: el concepto vigente más las propuestas "
                     "aprobadas sobre él")
    _instance_argument(effective_show)
    effective_show.add_argument("--character-id", required=True)
    effective_show.set_defaults(handler=_effective_show, action_name="character.effective.show")
    proposal = character_groups.add_parser("proposal", help="propuestas del agente")
    proposal_actions = proposal.add_subparsers(dest="proposal_action", required=True,
                                               metavar="acción")
    proposal_add = proposal_actions.add_parser(
        "add", help="registra una propuesta completa desde un JSON; no cambia nada hasta que la "
                    "apruebes")
    _instance_argument(proposal_add)
    proposal_add.add_argument("--character-id", required=True)
    proposal_add.add_argument("--input", required=True, type=Path, help="archivo JSON")
    proposal_add.set_defaults(handler=_proposal_add, action_name="character.proposal.add")
    proposal_list = proposal_actions.add_parser("list", help="lista las propuestas y su estado")
    _instance_argument(proposal_list)
    proposal_list.add_argument("--character-id", required=True)
    proposal_list.set_defaults(handler=_proposal_list, action_name="character.proposal.list")
    for name, handler, help_text in (
        ("show", _proposal_show, "muestra una propuesta con su base y su texto completos"),
        ("approve", _proposal_approve, "aprueba una propuesta; pide teclear una frase con un "
                                       "código"),
        ("reject", _proposal_reject, "rechaza una propuesta; pide teclear una frase con un "
                                     "código"),
    ):
        sub = proposal_actions.add_parser(name, help=help_text)
        _instance_argument(sub)
        sub.add_argument("--character-id", required=True)
        sub.add_argument("--proposal-id", required=True)
        sub.add_argument("--version", required=True, type=_positive_int)
        sub.set_defaults(handler=handler, action_name=f"character.proposal.{name}")
    draft = character_groups.add_parser(
        "draft", help="ficha del personaje (Markdown libre; el core no comprueba que cumpla las "
                      "normas)")
    draft_actions = draft.add_subparsers(dest="draft_action", required=True, metavar="acción")
    draft_create = draft_actions.add_parser(
        "create", help="registra una versión de la ficha sobre la composición efectiva vigente; "
                       "no publica nada")
    _instance_argument(draft_create)
    draft_create.add_argument("--character-id", required=True)
    draft_create.add_argument("--version", required=True, type=_positive_int)
    draft_create.add_argument("--composition-sha256", required=True,
                              help="hash de «character effective show»")
    draft_create.add_argument("--input", required=True, type=Path,
                              help="archivo Markdown, fuera del checkout y de la instancia")
    draft_create.set_defaults(handler=_draft_create, action_name="character.draft.create")
    draft_list = draft_actions.add_parser("list", help="lista las versiones de la ficha")
    _instance_argument(draft_list)
    draft_list.add_argument("--character-id", required=True)
    draft_list.set_defaults(handler=_draft_list, action_name="character.draft.list")
    draft_show = draft_actions.add_parser(
        "show", help="muestra una versión de la ficha para copiarla a mano (no acredita "
                     "publicación)")
    _instance_argument(draft_show)
    draft_show.add_argument("--character-id", required=True)
    draft_show.add_argument("--version", required=True, type=_positive_int)
    draft_show.set_defaults(handler=_draft_show, action_name="character.draft.show")
    staff = character_groups.add_parser("staff", help="respuestas del staff transcritas por ti")
    staff_actions = staff.add_subparsers(dest="staff_action", required=True, metavar="acción")
    staff_record = staff_actions.add_parser(
        "record", help="registra la respuesta que dio el staff a una versión de la ficha; pide "
                       "teclear una frase con un código (no autentica al staff)")
    _instance_argument(staff_record)
    staff_record.add_argument("--character-id", required=True)
    staff_record.add_argument("--version", required=True, type=_positive_int)
    staff_record.add_argument("--status", required=True, choices=("APPROVED", "REJECTED"),
                              help="REJECTED también abarca «cambios solicitados»")
    staff_record.add_argument("--input", required=True, type=Path,
                              help="JSON con draft_sha256, locator, observed_at y response")
    staff_record.set_defaults(handler=_staff_record, action_name="character.staff.record")

    narrative = commands.add_parser(
        "narrative", help="temas, semillas y borradores (no publica nada)")
    narrative_groups = narrative.add_subparsers(dest="narrative_group", required=True,
                                                metavar="grupo")
    topic = narrative_groups.add_parser("topic", help="temas de un personaje")
    topic_actions = topic.add_subparsers(dest="topic_action", required=True, metavar="acción")
    topic_create = topic_actions.add_parser("create", help="crea un tema vacío para un personaje")
    _instance_argument(topic_create)
    topic_create.add_argument("--character-id", required=True)
    topic_create.add_argument("--topic-id", required=True)
    topic_create.add_argument("--title", required=True)
    topic_create.set_defaults(handler=_topic_create, action_name="narrative.topic.create")
    topic_list = topic_actions.add_parser("list", help="lista los temas")
    _instance_argument(topic_list)
    topic_list.add_argument("--character-id")
    topic_list.set_defaults(handler=_topic_list, action_name="narrative.topic.list")
    topic_show = topic_actions.add_parser("show", help="muestra un tema y sus posts completos")
    _instance_argument(topic_show)
    topic_show.add_argument("--topic-id", required=True)
    topic_show.set_defaults(handler=_topic_show, action_name="narrative.topic.show")

    post = narrative_groups.add_parser("post", help="posts del tema (ajenos y propios)")
    post_actions = post.add_subparsers(dest="post_action", required=True, metavar="acción")
    post_record = post_actions.add_parser(
        "record", help="registra un post ajeno que has copiado; pide teclear una frase con un "
                       "código (no autentica al autor)")
    _instance_argument(post_record)
    post_record.add_argument("--topic-id", required=True)
    post_record.add_argument("--input", required=True, type=Path,
                             help="JSON con post_id, author_label, locator, observed_at y "
                                  "content, fuera del checkout y de la instancia")
    post_record.set_defaults(handler=_post_record, action_name="narrative.post.record")
    post_list = post_actions.add_parser("list", help="lista los posts en orden")
    _instance_argument(post_list)
    post_list.add_argument("--topic-id", required=True)
    post_list.set_defaults(handler=_post_list, action_name="narrative.post.list")
    post_show = post_actions.add_parser("show", help="muestra un post completo")
    _instance_argument(post_show)
    post_show.add_argument("--topic-id", required=True)
    post_show.add_argument("--post-id", required=True)
    post_show.set_defaults(handler=_post_show, action_name="narrative.post.show")

    seed = narrative_groups.add_parser("seed", help="ideas que aportas para el siguiente post")
    seed_actions = seed.add_subparsers(dest="seed_action", required=True, metavar="acción")
    seed_import = seed_actions.add_parser(
        "import", help="declara tus ideas para el siguiente post; pide teclear una frase con un "
                       "código")
    _instance_argument(seed_import)
    seed_import.add_argument("--topic-id", required=True)
    seed_import.add_argument("--input", required=True, type=Path,
                             help="JSON con seed_id, version, intent, tone, beats, details, "
                                  "ooc_constraints y pending_outcomes")
    seed_import.set_defaults(handler=_seed_import, action_name="narrative.seed.import")
    seed_list = seed_actions.add_parser("list", help="lista las semillas")
    _instance_argument(seed_list)
    seed_list.add_argument("--topic-id", required=True)
    seed_list.set_defaults(handler=_seed_list, action_name="narrative.seed.list")
    seed_show = seed_actions.add_parser("show", help="muestra una versión de una semilla")
    _instance_argument(seed_show)
    seed_show.add_argument("--topic-id", required=True)
    seed_show.add_argument("--seed-id", required=True)
    seed_show.add_argument("--version", required=True, type=_positive_int)
    seed_show.set_defaults(handler=_seed_show, action_name="narrative.seed.show")

    ndraft = narrative_groups.add_parser("draft", help="posts completos desarrollados por el "
                                                       "agente")
    ndraft_actions = ndraft.add_subparsers(dest="draft_action", required=True, metavar="acción")
    ndraft_create = ndraft_actions.add_parser(
        "create", help="registra un post desarrollado desde una semilla; no publica nada")
    _instance_argument(ndraft_create)
    ndraft_create.add_argument("--topic-id", required=True)
    ndraft_create.add_argument("--input", required=True, type=Path,
                               help="JSON del borrador, fuera del checkout y de la instancia")
    ndraft_create.set_defaults(handler=_narrative_draft_create,
                               action_name="narrative.draft.create")
    ndraft_list = ndraft_actions.add_parser("list", help="lista los borradores")
    _instance_argument(ndraft_list)
    ndraft_list.add_argument("--topic-id", required=True)
    ndraft_list.set_defaults(handler=_narrative_draft_list, action_name="narrative.draft.list")
    ndraft_show = ndraft_actions.add_parser(
        "show", help="muestra un borrador para copiarlo a mano (no acredita publicación)")
    _instance_argument(ndraft_show)
    ndraft_show.add_argument("--topic-id", required=True)
    ndraft_show.add_argument("--draft-id", required=True)
    ndraft_show.add_argument("--version", required=True, type=_positive_int)
    ndraft_show.set_defaults(handler=_narrative_draft_show, action_name="narrative.draft.show")

    publication = narrative_groups.add_parser("publication",
                                              help="publicaciones manuales confirmadas por ti")
    publication_actions = publication.add_subparsers(dest="publication_action", required=True,
                                                     metavar="acción")
    publication_confirm = publication_actions.add_parser(
        "confirm", help="tras publicar a mano, registra el texto final exacto; pide teclear una "
                        "frase con un código (no publica nada)")
    _instance_argument(publication_confirm)
    publication_confirm.add_argument("--topic-id", required=True)
    publication_confirm.add_argument("--draft-id", required=True)
    publication_confirm.add_argument("--version", required=True, type=_positive_int)
    publication_confirm.add_argument("--input", required=True, type=Path,
                                     help="JSON con post_id, draft_sha256, locator, observed_at "
                                          "y published_text")
    publication_confirm.set_defaults(handler=_publication_confirm,
                                     action_name="narrative.publication.confirm")
    return parser


def _workspace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, type=Path, help="carpeta del workspace")


def _instance_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--instance", required=True, type=Path, help="carpeta de la instancia")


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError("debe ser un entero positivo")
    return number


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


def _assimilation_extend(args: argparse.Namespace) -> int:
    dossier = load_manual_dossier(args.dossier)
    result = create_expansion_workspace(args.instance, dossier=dossier, dossier_dir=args.dossier,
                                        workspace=args.workspace, core_root=_checkout())
    workspace = result.workspace
    context = workspace.expansion
    forum_id = workspace.config.forum_id
    root = str(workspace.workspace_root)
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "base_snapshot_sha256": context.base.current.snapshot_sha256,
               "created": result.created, "dossier_version": context.delta.version,
               "forum_id": forum_id, "previous_dossier_version": context.delta.previous_version,
               "workspace": root})
        return EXIT_OK
    detail = (f"(snapshot base={context.base.current.snapshot_sha256}; expediente "
              f"{context.delta.previous_version} -> {context.delta.version})")
    if result.created:
        _line(f"Workspace de ampliación creado para «{forum_id}» en {root} {detail}.")
    else:
        _line(f"El workspace de ampliación de «{forum_id}» ya existía con el mismo contenido: "
              f"{root} {detail}.")
    return EXIT_OK


def _assimilation_status(args: argparse.Namespace) -> int:
    workspace = _load(args)
    forum_id = workspace.config.forum_id
    root = str(workspace.workspace_root)
    context = workspace.expansion
    if context is not None:
        closed = workspace.closure is not None
        if args.json:
            _emit({"ok": True, "action": args.action_name,
                   "base_snapshot_sha256": context.base.current.snapshot_sha256,
                   "corpus_revision": workspace.corpus_revision,
                   "dossier_version": context.delta.version, "forum_id": forum_id,
                   "integrity": "OK", "previous_dossier_version": context.delta.previous_version,
                   "round": context.round, "round_state": "CLOSED" if closed else "OPEN",
                   "workspace": root})
        else:
            _line(f"Workspace de ampliación íntegro del foro «{forum_id}» en {root} (ronda "
                  f"{context.round}; snapshot base={context.base.current.snapshot_sha256}; "
                  f"revisión del corpus {workspace.corpus_revision}; expediente "
                  f"{context.delta.previous_version} -> {context.delta.version}; estado "
                  f"{'CERRADO' if closed else 'ABIERTO'}).")
        return EXIT_OK
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
    context = workspace.expansion

    def is_new(declaration: _SourceDeclaration) -> bool:
        return context.delta.is_new(declaration.source_id, declaration.source_version)

    if args.json:
        sources = [_source_json(d) for d in declarations]
        if context is not None:
            sources = [{**s, "new_in_expansion": is_new(d)}
                       for s, d in zip(sources, declarations)]
        _emit({"ok": True, "action": args.action_name, "sources": sources,
               "workspace": str(workspace.workspace_root)})
    elif not declarations:
        _line("No hay fuentes.")
    else:
        for declaration in declarations:
            suffix = " | NUEVA" if context is not None and is_new(declaration) else ""
            _line(_source_line(declaration) + suffix)
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
                           expected_revision=workspace.corpus_revision, value=value,
                           context=workspace.expansion)
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
               "candidates": [_candidate_summary(c, workspace) for c in candidates],
               "corpus_revision": workspace.corpus_revision,
               "workspace": str(workspace.workspace_root)})
    elif not candidates:
        _line("No hay candidatos.")
    else:
        for candidate in candidates:
            _line(_candidate_line(candidate, workspace))
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
        decision = _decision_of(candidate, workspace)
        _emit({"ok": True, "action": args.action_name,
               "candidate": _candidate_record(candidate, include_hash=True),
               "corpus_revision": workspace.corpus_revision,
               "decision": None if decision is None else _decision_summary(decision),
               "workspace": str(workspace.workspace_root)})
        return EXIT_OK
    _line(_candidate_line(candidate, workspace))
    decision = _decision_of(candidate, workspace)
    _line("Decisión: pendiente" if decision is None else
          f"Decisión: {decision.review_status.value} (evidencia={decision.evidence.sha256})")
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


def _decision_of(candidate: AssimilationCandidate,
                 workspace: LoadedWorkspace | None) -> AssimilationDecision | None:
    if workspace is None:
        return None
    for decision in workspace.decisions:
        if decision.candidate_key == candidate.key:
            return decision
    return None


def _candidate_summary(candidate: AssimilationCandidate,
                       workspace: LoadedWorkspace | None = None) -> dict[str, object]:
    """`review_status` is the immutable state of the record; `decision` is the effective one."""
    decision = _decision_of(candidate, workspace)
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "class": candidate.candidate_class.value,
        "decision": None if decision is None else decision.review_status.value,
        "domain": candidate.domain.value,
        "review_status": candidate.review_status.value,
        "version": candidate.version,
    }


def _candidate_line(candidate: AssimilationCandidate,
                    workspace: LoadedWorkspace | None = None) -> str:
    line = (f"{candidate.candidate_id} v{candidate.version} | {candidate.candidate_class.value} | "
            f"{candidate.domain.value} | {candidate.review_status.value} | "
            f"sha256={candidate.candidate_sha256}")
    decision = _decision_of(candidate, workspace)
    if decision is not None:
        line += f" | decisión={decision.review_status.value}"
    return f"{line} | REQUIERE CONFIRMACIÓN" if candidate.requires_confirmation else line


# --- human decisions and closure --------------------------------------------------------------


class _SystemTerminal:
    """The real terminal. The CLI offers no flag, variable or file that replaces it."""

    def is_interactive(self) -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()

    def write(self, text: str) -> None:
        _write_exact(text)

    def read_line(self) -> str | None:
        line = sys.stdin.readline()
        return None if line == "" else line


def _reject_json(args: argparse.Namespace) -> None:
    if args.json:
        raise AssimilationError("INVALID_STATE", "las decisiones humanas no admiten --json: "
                                                 "ejecuta el comando en tu terminal y responde "
                                                 "a la confirmación")


def _candidate_decide(args: argparse.Namespace) -> int:
    _reject_json(args)
    workspace = _load(args)
    result = record_candidate_decision(
        workspace.workspace_root / CORPUS_STATE, dossier=workspace.dossier,
        expected_revision=workspace.corpus_revision, candidate_id=args.candidate_id,
        version=args.version, review_status=args.review_status, terminal=_SystemTerminal(),
        context=workspace.expansion)
    decision = result.decision
    prefix = "Decisión registrada" if result.created else "Decisión ya existente"
    _line(f"{prefix}: {decision.candidate_id} v{decision.candidate_version} | "
          f"{decision.review_status.value} | sha256={decision.candidate_sha256}")
    _line(f"Revisión del corpus: {result.corpus_revision}.")
    return EXIT_OK


def _assimilation_close(args: argparse.Namespace) -> int:
    _reject_json(args)
    workspace = _load(args)
    context = workspace.expansion
    if context is not None:
        expansion = close_expansion(
            workspace.workspace_root / CORPUS_STATE, dossier=workspace.dossier, context=context,
            expected_revision=workspace.corpus_revision, terminal=_SystemTerminal())
        snapshot = expansion.snapshot
        prefix = "Ampliación cerrada" if expansion.created else "Ampliación ya cerrada"
        _line(f"{prefix}: {workspace.config.forum_id} | ronda {snapshot.ordinal} | snapshot "
              f"padre {snapshot.parent_snapshot_sha256} | snapshot "
              f"sha256={snapshot.snapshot_sha256}")
        _line(f"Revisión del corpus: {expansion.corpus_revision}.")
        return EXIT_OK
    result = close_assimilation(
        workspace.workspace_root / CORPUS_STATE, dossier=workspace.dossier,
        expected_revision=workspace.corpus_revision, terminal=_SystemTerminal())
    closure = result.closure
    prefix = "Asimilación cerrada" if result.created else "Asimilación ya cerrada"
    _line(f"{prefix}: {workspace.config.forum_id} | revisión base {closure.base_revision} | "
          f"snapshot sha256={closure.snapshot_sha256}")
    _line(f"Revisión del corpus: {result.corpus_revision}.")
    return EXIT_OK


def _decision_list(args: argparse.Namespace) -> int:
    workspace = _load(args)
    decisions = workspace.decisions
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "decisions": [_decision_summary(d) for d in decisions],
               "corpus_revision": workspace.corpus_revision,
               "workspace": str(workspace.workspace_root)})
    elif not decisions:
        _line("No hay decisiones.")
    else:
        for decision in decisions:
            _line(f"{decision.candidate_id} v{decision.candidate_version} | "
                  f"{decision.review_status.value} | sha256={decision.candidate_sha256} | "
                  f"evidencia={decision.evidence.sha256}")
    return EXIT_OK


def _decision_summary(decision: AssimilationDecision) -> dict[str, object]:
    return {
        "candidate_id": decision.candidate_id,
        "candidate_sha256": decision.candidate_sha256,
        "candidate_version": decision.candidate_version,
        "decision_id": decision.decision_id,
        "evidence_sha256": decision.evidence.sha256,
        "review_status": decision.review_status.value,
    }


# --- instance -------------------------------------------------------------------------------


def _load_instance(args: argparse.Namespace) -> LoadedInstance:
    return load_instance(args.instance, expected_core_root=_checkout())


def _instance_init(args: argparse.Namespace) -> int:
    result = create_instance(args.workspace, output=args.output, core_root=_checkout(),
                             instructions_version=args.instructions_version)
    instance = result.instance
    forum_id = instance.config.forum_id
    root = str(instance.instance_root)
    snapshot = instance.config.corpus.snapshot_sha256
    if args.json:
        _emit({"ok": True, "action": args.action_name, "created": result.created,
               "forum_id": forum_id, "instance": root, "snapshot_sha256": snapshot})
    elif result.created:
        _line(f"Instancia creada para el foro «{forum_id}» en {root} (snapshot sha256={snapshot}).")
    else:
        _line(f"La instancia del foro «{forum_id}» ya existía con el mismo contenido: {root} "
              f"(snapshot sha256={snapshot}).")
    return EXIT_OK


def _instance_status(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    forum_id = instance.config.forum_id
    root = str(instance.instance_root)
    snapshot = instance.config.corpus.snapshot_sha256
    if args.json:
        _emit({"ok": True, "action": args.action_name, "corpus_revision": instance.corpus_revision,
               "forum_id": forum_id, "instance": root, "integrity": "OK",
               "snapshot_sha256": snapshot})
    else:
        _line(f"Instancia íntegra del foro «{forum_id}» en {root} (revisión del corpus "
              f"{instance.corpus_revision}; snapshot sha256={snapshot}).")
    return EXIT_OK


def _instance_update(args: argparse.Namespace) -> int:
    if args.json:
        raise InstanceError("INVALID_STATE", "la actualización de una instancia no admite --json: "
                                             "ejecuta el comando en tu terminal y responde a la "
                                             "confirmación")
    result = update_instance(args.instance, workspace_root=args.workspace,
                             core_root=_checkout(), terminal=_SystemTerminal())
    instance = result.instance
    snapshot = instance.config.corpus.snapshot_sha256
    detail = (f"expediente {instance.config.dossier_version} | personajes "
              f"{len(instance.characters)}.")
    if result.updated:
        _line(f"Instancia actualizada: {instance.config.forum_id} | snapshot "
              f"{result.previous_snapshot_sha256} -> {snapshot} | {detail}")
    else:
        _line(f"Instancia ya actualizada: {instance.config.forum_id} | snapshot {snapshot} | "
              f"{detail}")
    return EXIT_OK


def _instance_instructions_update(args: argparse.Namespace) -> int:
    if args.json:
        raise InstanceError("INVALID_STATE", "la actualización humana de instrucciones no admite "
                                             "--json: ejecuta el comando en tu terminal y responde "
                                             "a la confirmación")
    result = update_instance_instructions(args.instance, core_root=_checkout(),
                                          terminal=_SystemTerminal())
    forum_id = result.instance.config.forum_id
    new = result.instructions
    if result.updated:
        _line(f"Instrucciones actualizadas: {forum_id} | v{result.previous.version} -> "
              f"v{new.version} | conjunto sha256={new.instructions_sha256}.")
    else:
        _line(f"Instrucciones ya actualizadas: {forum_id} | v{new.version} | conjunto "
              f"sha256={new.instructions_sha256}.")
    return EXIT_OK


def _instance_corpus_history(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    chain = closed_corpus_of(instance)
    rows = []
    previous = None
    for snapshot in chain.snapshots:
        start_c = 0 if previous is None else previous.candidate_count
        start_d = 0 if previous is None else previous.decision_count
        rows.append((snapshot, snapshot.candidate_count - start_c,
                     snapshot.decision_count - start_d))
        previous = snapshot
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "current_snapshot_sha256": chain.current.snapshot_sha256,
               "instance": str(instance.instance_root),
               "snapshots": [{
                   "candidate_count": s.candidate_count, "candidate_delta": dc,
                   "corpus_revision": s.corpus_revision, "decision_count": s.decision_count,
                   "decision_delta": dd, "dossier_snapshot_sha256": s.dossier.snapshot_sha256,
                   "dossier_version": s.dossier.dossier_version, "format": s.format,
                   "ordinal": s.ordinal, "parent_snapshot_sha256": s.parent_snapshot_sha256,
                   "snapshot_sha256": s.snapshot_sha256,
               } for s, dc, dd in rows]})
        return EXIT_OK
    for s, dc, dd in rows:
        parent = "null" if s.parent_snapshot_sha256 is None else s.parent_snapshot_sha256
        _line(f"ronda {s.ordinal} | {s.format} | "
              f"expediente={json.dumps(s.dossier.dossier_version, ensure_ascii=False)} | "
              f"dossier_sha256={s.dossier.snapshot_sha256} | snapshot={s.snapshot_sha256} | "
              f"padre={parent} | candidatos={s.candidate_count} (+{dc}) | "
              f"decisiones={s.decision_count} (+{dd})")
    return EXIT_OK


def _instance_corpus_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    entries = approved_corpus(instance)
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "candidates": [_approved_summary(e) for e in entries],
               "corpus_revision": instance.corpus_revision, "instance": str(instance.instance_root),
               "snapshot_sha256": instance.config.corpus.snapshot_sha256})
    elif not entries:
        _line("No hay candidatos aprobados vigentes.")
    else:
        for entry in entries:
            _line(_approved_line(entry))
    return EXIT_OK


def _instance_corpus_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    entry = get_approved_candidate(instance, candidate_id=args.candidate_id, version=args.version)
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "candidate": _candidate_record(entry.candidate, include_hash=True),
               "corpus_revision": instance.corpus_revision,
               "decision": _decision_summary(entry.decision),
               "effective_review_status": "APPROVED", "instance": str(instance.instance_root),
               "snapshot_sha256": instance.config.corpus.snapshot_sha256})
        return EXIT_OK
    _line(_approved_line(entry))
    _line(f"Decisión: APPROVED (evidencia={entry.decision.evidence.sha256}).")
    for index, citation in enumerate(entry.candidate.citations, start=1):
        passage = "null" if citation.declared_passage is None else citation.declared_passage
        _line(f"Cita {index}: {citation.dossier_section.value} | {citation.source_id} | "
              f"v{citation.source_version} | pasaje={passage} | sha256={citation.source_sha256} | "
              f"caracteres {citation.start}-{citation.end}")
        _exact_block(f"Cita {index} (exacta, hasta «Fin de la cita {index}.»):", citation.quote,
                     f"Fin de la cita {index}.")
    _exact_block("Texto (exacto, hasta «Fin del texto.»):", entry.candidate.text, "Fin del texto.")
    return EXIT_OK


def _exact_block(header: str, content: str, footer: str) -> None:
    _line(header)
    _write_exact(content if content.endswith("\n") else content + "\n")
    _line(footer)


def _approved_summary(entry: ApprovedCorpusEntry) -> dict[str, object]:
    candidate = entry.candidate
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "class": candidate.candidate_class.value,
        "decision": "APPROVED",
        "domain": candidate.domain.value,
        "requires_confirmation": candidate.requires_confirmation,
        "scope": candidate.scope,
        "version": candidate.version,
    }


def _approved_line(entry: ApprovedCorpusEntry) -> str:
    candidate = entry.candidate
    line = (f"{candidate.candidate_id} v{candidate.version} | {candidate.candidate_class.value} | "
            f"{candidate.domain.value} | APPROVED | "
            f"scope={json.dumps(candidate.scope, ensure_ascii=False)} | "
            f"sha256={candidate.candidate_sha256}")
    return f"{line} | REQUIERE CONFIRMACIÓN" if candidate.requires_confirmation else line


# --- character --------------------------------------------------------------------------------


def _concept_import(args: argparse.Namespace) -> int:
    if args.json:
        raise CharacterError("INVALID_STATE", "las declaraciones humanas de concepto no admiten "
                                              "--json: ejecuta el comando en tu terminal y "
                                              "responde a la confirmación")
    result = import_concept(args.instance, expected_core_root=_checkout(),
                            character_id=args.character_id, version=args.version,
                            input_path=args.input, terminal=_SystemTerminal())
    prefix = "Concepto importado" if result.created else "Concepto ya existente"
    _line(f"{prefix}: {_concept_line(args.character_id, result.concept)}")
    _line(f"Revisión del personaje: {result.character.state_revision}.")
    return EXIT_OK


def _concept_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    concepts = list_concepts(instance, character_id=args.character_id)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "concepts": [concept_summary(c) for c in concepts],
               "instance": str(instance.instance_root), "state_revision": revision})
    else:
        for concept in concepts:
            _line(_concept_line(args.character_id, concept))
    return EXIT_OK


def _concept_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    concept = get_concept(instance, character_id=args.character_id, version=args.version)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "concept": concept_record(args.character_id, concept),
               "instance": str(instance.instance_root), "state_revision": revision})
        return EXIT_OK
    _line(_concept_line(args.character_id, concept))
    _line(f"Evidencia: {concept.evidence.sha256}")
    _exact_block("Texto (exacto, hasta «Fin del concepto.»):", concept.text, "Fin del concepto.")
    return EXIT_OK


def _effective_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    composition = get_effective_composition(instance, character_id=args.character_id)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "composition": composition_record(composition),
               "instance": str(instance.instance_root), "state_revision": revision})
        return EXIT_OK
    _line(f"Composición efectiva: {args.character_id} | {_concept_ref(composition)} | "
          f"sha256={composition.composition_sha256} | "
          f"pasos={len(composition.applied_proposals)} | bytes={composition.utf8_size}")
    for index, step in enumerate(composition.applied_proposals, start=1):
        _line(f"Paso {index}: {step.proposal.proposal_id} v{step.proposal.version} | "
              f"propuesta={step.proposal.proposal_sha256} | "
              f"resultado={step.proposal.result_composition_sha256} | "
              f"evidencia={step.decision.evidence.sha256}")
    _exact_block("Texto efectivo (exacto, hasta «Fin de la composición efectiva.»):",
                 composition.text, "Fin de la composición efectiva.")
    return EXIT_OK


def _proposal_add(args: argparse.Namespace) -> int:
    value = load_strict_json(args.input)
    result = add_proposal(args.instance, expected_core_root=_checkout(),
                          character_id=args.character_id, value=value)
    proposal = result.proposal
    view = result.character.state.view(proposal.proposal_id, proposal.version)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "created": result.created,
               "instance": str(result.character.character_root.parent.parent),
               "proposal": _proposal_summary(view),
               "state_revision": result.character.state_revision})
        return EXIT_OK
    prefix = "Propuesta añadida" if result.created else "Propuesta ya existente"
    _line(f"{prefix}: {_proposal_line(view)}")
    _line(f"Revisión del personaje: {result.character.state_revision}.")
    return EXIT_OK


def _proposal_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    views = list_proposals(instance, character_id=args.character_id)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "instance": str(instance.instance_root),
               "proposals": [_proposal_summary(v) for v in views], "state_revision": revision})
        return EXIT_OK
    if not views:
        _line(f"No hay propuestas para «{args.character_id}».")
    for view in views:
        _line(_proposal_line(view))
    return EXIT_OK


def _proposal_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    view = get_proposal(instance, character_id=args.character_id,
                        proposal_id=args.proposal_id, version=args.version)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "applied_to_effective": view.applied_to_effective,
               "base": composition_record(view.base), "character_id": args.character_id,
               "decision": None if view.decision is None else decision_record(view.decision),
               "instance": str(instance.instance_root), "proposal": proposal_record(view.proposal),
               "status": view.status.value, "state_revision": revision})
        return EXIT_OK
    _line(_proposal_line(view))
    if view.decision is None:
        _line(f"Decisión: ninguna (estado {view.status.value}).")
    else:
        _line(f"Decisión: {view.decision.review_status.value} "
              f"(evidencia={view.decision.evidence.sha256}).")
    for line in citation_lines(instance, view.proposal):
        _line(line)
    _write_exact(proposal_blocks(view))
    return EXIT_OK


def _proposal_approve(args: argparse.Namespace) -> int:
    return _proposal_decide(args, ReviewStatus.APPROVED)


def _proposal_reject(args: argparse.Namespace) -> int:
    return _proposal_decide(args, ReviewStatus.REJECTED)


def _proposal_decide(args: argparse.Namespace, review_status: ReviewStatus) -> int:
    if args.json:
        raise CharacterError("INVALID_STATE", "las decisiones humanas sobre propuestas no admiten "
                                              "--json: ejecuta el comando en tu terminal y "
                                              "responde a la confirmación")
    result = record_proposal_decision(args.instance, expected_core_root=_checkout(),
                                      character_id=args.character_id,
                                      proposal_id=args.proposal_id, version=args.version,
                                      review_status=review_status, terminal=_SystemTerminal())
    word = "aprobada" if review_status is ReviewStatus.APPROVED else "rechazada"
    prefix = f"Propuesta {word}" if result.created else f"Propuesta ya {word}"
    decision = result.decision
    _line(f"{prefix}: {decision.proposal_id} v{decision.proposal_version} | "
          f"sha256={decision.proposal_sha256}")
    _line(f"Composición efectiva: {result.effective.composition_sha256}.")
    _line(f"Revisión del personaje: {result.character.state_revision}.")
    return EXIT_OK


def _draft_create(args: argparse.Namespace) -> int:
    result = create_draft(args.instance, expected_core_root=_checkout(),
                          character_id=args.character_id, version=args.version,
                          composition_sha256=args.composition_sha256, input_path=args.input)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "created": result.created, "draft": draft_view_record(result.draft),
               "instance": str(result.character.character_root.parent.parent),
               "state_revision": result.character.state_revision})
        return EXIT_OK
    prefix = "Ficha creada" if result.created else "Ficha ya existente"
    _line(f"{prefix}: {_draft_line(result.draft)}")
    _line(f"Revisión del personaje: {result.character.state_revision}.")
    _write_exact(sheet_block(result.draft))
    return EXIT_OK


def _draft_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    views = list_drafts(instance, character_id=args.character_id)
    revision = _character_revision(instance, args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "drafts": [draft_summary(v) for v in views],
               "instance": str(instance.instance_root), "state_revision": revision})
        return EXIT_OK
    if not views:
        _line(f"No hay fichas para «{args.character_id}».")
    for view in views:
        _line(_draft_line(view))
    return EXIT_OK


def _draft_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    view = get_draft(instance, character_id=args.character_id, version=args.version)
    revision = _character_revision(instance, args.character_id)
    response = view.staff_response
    if args.json:
        _emit({"ok": True, "action": args.action_name, "character_id": args.character_id,
               "draft": draft_view_record(view), "instance": str(instance.instance_root),
               "staff_response": None if response is None else staff_response_record(response),
               "state_revision": revision})
        return EXIT_OK
    _line(_draft_line(view))
    if response is None:
        _line("Respuesta del staff: ninguna.")
    else:
        _line(f"Respuesta del staff: {response.review_status.value} | "
              f"respuesta={response.response_sha256} | registro={response.staff_review_sha256} | "
              f"locator={json.dumps(response.evidence.locator, ensure_ascii=False)} | "
              f"observada={response.evidence.observed_at.isoformat()}.")
    for line in draft_reference_lines(instance, view):
        _line(line)
    _write_exact(sheet_block(view))
    if response is not None:
        _write_exact(response_block(response.response))
    return EXIT_OK


def _staff_record(args: argparse.Namespace) -> int:
    if args.json:
        raise CharacterError("INVALID_STATE", "las respuestas de staff transcritas no admiten "
                                              "--json: ejecuta el comando en tu terminal y "
                                              "responde a la confirmación")
    result = record_staff_response(args.instance, expected_core_root=_checkout(),
                                   character_id=args.character_id, version=args.version,
                                   review_status=ReviewStatus(args.status), input_path=args.input,
                                   terminal=_SystemTerminal())
    prefix = ("Respuesta del staff registrada" if result.created
              else "Respuesta del staff ya registrada")
    response = result.response
    _line(f"{prefix}: {DRAFT_ID} v{response.draft_version} | {response.review_status.value} | "
          f"respuesta={response.response_sha256} | registro={response.staff_review_sha256}")
    _line(_draft_line(result.draft))
    _line(f"Revisión del personaje: {result.character.state_revision}.")
    return EXIT_OK


def _draft_line(view: CharacterDraftView) -> str:
    effective = view.effective
    return (f"{DRAFT_ID} v{view.version} | {effective.lifecycle.value} | "
            f"{'CURRENT' if view.current else 'SUPERSEDED'} | {effective.review_status.value} | "
            f"{effective.publication_status.value} | "
            f"composición={view.record.composition_sha256} | sha256={view.record.draft_sha256} | "
            f"bytes={view.record.utf8_size} | corpus={len(view.record.corpus_refs)}")


def _proposal_line(view: ProposalView) -> str:
    proposal = view.proposal
    return (f"{proposal.proposal_id} v{proposal.version} | {view.status.value} | "
            f"{_concept_ref(proposal)} | base={proposal.base_composition_sha256} | "
            f"resultado={proposal.result_composition_sha256} | "
            f"sha256={proposal.proposal_sha256} | citas={len(proposal.citations)} | "
            f"aplicada={'SÍ' if view.applied_to_effective else 'NO'}")


def _proposal_summary(view: ProposalView) -> dict[str, object]:
    proposal = view.proposal
    return {
        "applied_to_effective": view.applied_to_effective,
        "base_composition_sha256": proposal.base_composition_sha256,
        "citation_count": len(proposal.citations),
        "concept": proposal.concept.as_json(),
        "decision": None if view.decision is None else view.decision.review_status.value,
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.proposal_sha256,
        "result_composition_sha256": proposal.result_composition_sha256,
        "status": view.status.value,
        "version": proposal.version,
    }


def _concept_ref(item: EffectiveComposition | CharacterProposal) -> str:
    return f"concepto=v{item.concept.version}:{item.concept.concept_sha256}"


def _character_revision(instance: LoadedInstance, character_id: str) -> int:
    for character in instance.characters:
        if character.state.character_id == character_id:
            return character.state_revision
    raise CharacterError("INVALID_STATE", f"no existe el personaje «{character_id}» en esta "
                                          "instancia")


def _concept_line(character_id: str, concept: ConceptVersion) -> str:
    return (f"{character_id} v{concept.version} | {concept.authorship.value} | "
            f"sha256={concept.concept_sha256} | bytes={concept.utf8_size}")


# --- narrative --------------------------------------------------------------------------------


def _topic_create(args: argparse.Namespace) -> int:
    result = create_topic(args.instance, expected_core_root=_checkout(),
                          character_id=args.character_id, topic_id=args.topic_id,
                          title=args.title)
    if _narrative_mutation(args, result.topic, result.created,
                           {"topic": topic_summary(result.topic.state)}):
        return EXIT_OK
    prefix = "Tema creado" if result.created else "Tema ya existente"
    _line(f"{prefix}: {_topic_line(result.topic)}")
    _line(f"Revisión del tema: {result.topic.state_revision}.")
    return EXIT_OK


def _topic_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    topics = list_topics(instance, character_id=args.character_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "instance": str(instance.instance_root),
               "topics": [topic_summary(t.state) for t in topics]})
        return EXIT_OK
    if not topics:
        _line("No hay temas en esta instancia." if args.character_id is None
              else f"No hay temas para «{args.character_id}».")
    for topic in topics:
        _line(_topic_line(topic))
    return EXIT_OK


def _topic_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    topic = get_topic(instance, topic_id=args.topic_id)
    posts = topic.state.replay.posts
    if args.json:
        _emit({"ok": True, "action": args.action_name, "instance": str(instance.instance_root),
               "posts": [post_summary(p) for p in posts], "state_revision": topic.state_revision,
               "topic": topic_summary(topic.state), "topic_id": args.topic_id})
        return EXIT_OK
    _line(_topic_line(topic))
    if not posts:
        _line(f"No hay posts para «{args.topic_id}».")
    for post in posts:
        _line(_post_line(post))
        _exact_block(f"Post p{post.position} (exacto, hasta «Fin del post p{post.position}.»):",
                     post.content, f"Fin del post p{post.position}.")
    return EXIT_OK


def _post_record(args: argparse.Namespace) -> int:
    if args.json:
        raise NarrativeError("INVALID_STATE", "los posts ajenos transcritos no admiten --json: "
                                              "ejecuta el comando en tu terminal y responde a la "
                                              "confirmación")
    result = record_external_post(args.instance, expected_core_root=_checkout(),
                                  topic_id=args.topic_id, input_path=args.input,
                                  terminal=_SystemTerminal())
    prefix = "Post ajeno registrado" if result.created else "Post ajeno ya existente"
    _line(f"{prefix}: {_post_line(result.topic.state.post(result.post.post_id))}")
    _line(f"Revisión del tema: {result.topic.state_revision}.")
    return EXIT_OK


def _post_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    posts = list_posts(instance, topic_id=args.topic_id)
    if _narrative_list(args, instance, "posts", [post_summary(p) for p in posts]):
        return EXIT_OK
    if not posts:
        _line(f"No hay posts para «{args.topic_id}».")
    for post in posts:
        _line(_post_line(post))
    return EXIT_OK


def _post_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    post = get_post(instance, topic_id=args.topic_id, post_id=args.post_id)
    topic = get_topic(instance, topic_id=args.topic_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "instance": str(instance.instance_root),
               "post": post_summary(post), "state_revision": topic.state_revision,
               "topic_id": args.topic_id})
        return EXIT_OK
    source = post.source
    _line(_post_line(post))
    if isinstance(source, ExternalPost):
        _line(f"Autor declarado: {json.dumps(source.author_label, ensure_ascii=False)}")
    else:
        _line(f"Borrador: {source.draft_id} v{source.draft_version} | "
              f"sha256={source.draft_sha256} | "
              f"coincidencia exacta={'SÍ' if source.content_matches_draft else 'NO'}")
    _line(f"Evidencia: {source.evidence.source_id} | sha256={source.evidence.sha256}")
    _exact_block("Texto (exacto, hasta «Fin del texto.»):", post.content, "Fin del texto.")
    return EXIT_OK


def _seed_import(args: argparse.Namespace) -> int:
    if args.json:
        raise NarrativeError("INVALID_STATE", "las declaraciones humanas de semillas narrativas "
                                              "no admiten --json: ejecuta el comando en tu "
                                              "terminal y responde a la confirmación")
    result = import_human_seed(args.instance, expected_core_root=_checkout(),
                               topic_id=args.topic_id, input_path=args.input,
                               terminal=_SystemTerminal())
    prefix = "Semilla importada" if result.created else "Semilla ya existente"
    _line(f"{prefix}: {_seed_line(result.seed)}")
    _line(f"Revisión del tema: {result.topic.state_revision}.")
    return EXIT_OK


def _seed_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    seeds = list_seeds(instance, topic_id=args.topic_id)
    if _narrative_list(args, instance, "seeds", [seed_summary(s) for s in seeds]):
        return EXIT_OK
    if not seeds:
        _line(f"No hay semillas para «{args.topic_id}».")
    for seed in seeds:
        _line(_seed_line(seed))
    return EXIT_OK


def _seed_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    seed = get_seed(instance, topic_id=args.topic_id, seed_id=args.seed_id,
                    version=args.version)
    topic = get_topic(instance, topic_id=args.topic_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "instance": str(instance.instance_root),
               "seed": seed_summary(seed), "state_revision": topic.state_revision,
               "topic_id": args.topic_id})
        return EXIT_OK
    _line(_seed_line(seed))
    _line(f"Intención: {json.dumps(seed.intent, ensure_ascii=False)}")
    _line(f"Tono: {json.dumps(seed.tone, ensure_ascii=False)}")
    for label, items in (("Giros", seed.beats), ("Detalles", seed.details),
                         ("Restricciones OOC", seed.ooc_constraints),
                         ("Resultados pendientes", seed.pending_outcomes)):
        _line(f"{label}: {json.dumps(list(items), ensure_ascii=False)}")
    return EXIT_OK


def _narrative_draft_create(args: argparse.Namespace) -> int:
    result = create_narrative_draft(args.instance, expected_core_root=_checkout(),
                                    topic_id=args.topic_id, input_path=args.input)
    if _narrative_mutation(args, result.topic, result.created,
                           {"draft": narrative_draft_summary(result.draft)}):
        return EXIT_OK
    prefix = "Borrador creado" if result.created else "Borrador ya existente"
    _line(f"{prefix}: {_narrative_draft_line(result.draft)}")
    _line(f"Revisión del tema: {result.topic.state_revision}.")
    return EXIT_OK


def _narrative_draft_list(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    views = list_narrative_drafts(instance, topic_id=args.topic_id)
    if _narrative_list(args, instance, "drafts", [narrative_draft_summary(v) for v in views]):
        return EXIT_OK
    if not views:
        _line(f"No hay borradores para «{args.topic_id}».")
    for view in views:
        _line(_narrative_draft_line(view))
    return EXIT_OK


def _narrative_draft_show(args: argparse.Namespace) -> int:
    instance = _load_instance(args)
    view = get_narrative_draft(instance, topic_id=args.topic_id, draft_id=args.draft_id,
                               version=args.version)
    topic = get_topic(instance, topic_id=args.topic_id)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "draft": narrative_draft_summary(view),
               "instance": str(instance.instance_root), "state_revision": topic.state_revision,
               "topic_id": args.topic_id})
        return EXIT_OK
    record = view.record
    _line(_narrative_draft_line(view))
    _line(f"Contexto: sha256={record.context_sha256} | posts={len(record.context)}")
    _line(f"Ficha: v{record.sheet.version} | sha256={record.sheet.draft_sha256} | "
          f"staff={record.sheet.staff_review_sha256} | "
          f"revisión del personaje={record.character_revision}")
    if not record.citations:
        _line("Citas: ninguna.")
    for citation in record.citations:
        _line(f"Cita: {citation.candidate_id} v{citation.version} | "
              f"sha256={citation.candidate_sha256}")
    published = view.published
    if published is None:
        _line("Publicación: ninguna.")
    else:
        _line(f"Publicación: {view.publication.value} | p{published.position} | "
              f"{published.post_id} | sha256={published.content_sha256}")
    _exact_block("POST PARA COPIA MANUAL (no acredita publicación, hasta «Fin del post.»):",
                 record.publishable_text, "Fin del post.")
    _line(f"NO PUBLICAR — OOC: {json.dumps(list(record.ooc_notes), ensure_ascii=False)}")
    _line(f"NO PUBLICAR — privado: {json.dumps(list(record.private_notes), ensure_ascii=False)}")
    _line("NO PUBLICAR — resultados pendientes: "
          f"{json.dumps(list(record.pending_outcomes), ensure_ascii=False)}")
    return EXIT_OK


def _publication_confirm(args: argparse.Namespace) -> int:
    if args.json:
        raise NarrativeError("INVALID_STATE", "las confirmaciones de publicación manual no "
                                              "admiten --json: ejecuta el comando en tu terminal "
                                              "y responde a la confirmación")
    result = confirm_narrative_publication(args.instance, expected_core_root=_checkout(),
                                           topic_id=args.topic_id, draft_id=args.draft_id,
                                           version=args.version, input_path=args.input,
                                           terminal=_SystemTerminal())
    prefix = "Publicación confirmada" if result.created else "Publicación ya confirmada"
    state = result.topic.state
    _line(f"{prefix}: {_post_line(state.post(result.publication.post_id))}")
    _line(_narrative_draft_line(state.draft_view(args.draft_id, args.version)))
    _line(f"Revisión del tema: {result.topic.state_revision}.")
    return EXIT_OK


def _narrative_mutation(args: argparse.Namespace, topic: LoadedNarrativeTopic, created: bool,
                        payload: dict[str, object]) -> bool:
    if not args.json:
        return False
    _emit({"ok": True, "action": args.action_name, "created": created,
           "instance": str(Path(topic.topic_root).parent.parent.parent),
           "state_revision": topic.state_revision, "topic_id": topic.state.topic_id, **payload})
    return True


def _narrative_list(args: argparse.Namespace, instance: LoadedInstance, key: str,
                    items: list) -> bool:
    if not args.json:
        return False
    topic = get_topic(instance, topic_id=args.topic_id)
    _emit({"ok": True, "action": args.action_name, "instance": str(instance.instance_root),
           key: items, "state_revision": topic.state_revision, "topic_id": args.topic_id})
    return True


def _topic_line(topic: LoadedNarrativeTopic) -> str:
    state = topic.state
    return (f"{state.topic_id} | personaje={state.header.character_id} | "
            f"posts={len(state.replay.posts)} | semillas={len(state.seeds)} | "
            f"borradores={len(state.drafts)} | publicaciones={len(state.publications)} | "
            f"contexto={topic_summary(state)['context_sha256']} | "
            f"revisión={topic.state_revision} | "
            f"título={json.dumps(state.header.title, ensure_ascii=False)}")


def _post_line(post: NarrativePostView) -> str:
    source = post.source
    return (f"p{post.position} | {post.author.value} | {post.post_id} | "
            f"sha256={source.content_sha256} | bytes={source.utf8_size} | "
            f"locator={json.dumps(source.evidence.locator, ensure_ascii=False)} | "
            f"observada={source.evidence.observed_at.isoformat()}")


def _seed_line(seed: HumanSeed) -> str:
    return (f"{seed.seed_id} v{seed.version} | {seed.mode.value} | sha256={seed.seed_sha256} | "
            f"contexto={seed.context_sha256} | posts={len(seed.context)} | "
            f"pendientes={len(seed.pending_outcomes)}")


def _narrative_draft_line(view: NarrativeDraftView) -> str:
    record = view.record
    return (f"{record.draft_id} v{record.version} | {view.lifecycle.value} | "
            f"publicación={view.publication.value} | posición={record.target_position} | "
            f"semilla={record.seed_id}:v{record.seed_version}:{record.seed_sha256} | "
            f"composición={record.composition_sha256} | "
            f"ficha=v{record.sheet.version}:{record.sheet.draft_sha256} | "
            f"sha256={record.draft_sha256} | bytes={record.utf8_size} | "
            f"citas={len(record.citations)} | pendientes={len(record.pending_outcomes)}")


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
