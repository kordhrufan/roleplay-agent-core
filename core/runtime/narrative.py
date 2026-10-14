"""Narrative operations on a forum instance (7a): topics, transcribed posts, human seeds, drafts
developed by the agent and manual publications confirmed by the person.

Recording someone else's post, declaring a seed and confirming a publication are human actions
under barrier A: the exact content is shown and the person types a phrase with a one-time code.
That records an explicit human declaration; it does not authenticate who wrote a post, who
answered or that something was published. Creating a topic and registering a draft are not
human actions. Nothing here publishes: `PublicationPort` only fixes the future boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.character.models import (
    CharacterError,
    CorpusCandidateRef,
    _check_free_text,
    _check_sha256,
    check_locator,
    parse_observed_at,
)
from core.memory.narrative import (
    CharacterSheetRef,
    ExternalPost,
    HumanSeed,
    LoadedNarrativeTopic,
    NarrativeDraftRecord,
    NarrativeDraftView,
    NarrativeError,
    NarrativePostView,
    NarrativePublication,
    TopicHeader,
    TopicState,
    check_label,
    check_narrative_id,
    context_sha256,
    decode_topic_state,
    draft_semantics,
    encode_topic_content,
    make_external_post,
    make_publication,
    make_seed,
    seed_semantics,
    text_sha256,
)
from core.review.models import DraftLifecycle, ReviewStatus
from core.runtime.assimilation import (
    AssimilationError,
    Terminal,
    _corpus_lock,
    _require_interactive,
    _require_unlocked,
    confirm_human_action,
)
from core.runtime.character import _read_external, find_character
from core.runtime.events import append_event, folder_guard, publish_new_folder
from core.runtime.instance import (
    NARRATIVE_DIR,
    TOPIC_STATE,
    TOPICS_DIR,
    InstanceError,
    LoadedInstance,
    get_approved_candidate,
    load_instance,
    require_no_update,
)
from core.runtime.persistence import (
    PersistenceError,
    encode_state,
    load_state,
    parse_strict_json,
)
from core.runtime.workspace import WorkspaceError, _publish

_POST_INPUT_KEYS = frozenset({"author_label", "content", "locator", "observed_at", "post_id"})
_SEED_INPUT_KEYS = frozenset({"beats", "details", "intent", "ooc_constraints",
                              "pending_outcomes", "seed_id", "tone", "version"})
_DRAFT_INPUT_KEYS = frozenset({"citations", "composition_sha256", "context_sha256", "draft_id",
                               "ooc_notes", "pending_outcomes", "private_notes",
                               "publishable_text", "seed_id", "seed_sha256", "seed_version",
                               "sheet_sha256", "sheet_version", "version"})
_PUBLICATION_INPUT_KEYS = frozenset({"draft_sha256", "locator", "observed_at", "post_id",
                                     "published_text"})
_CITATION_INPUT_KEYS = frozenset({"candidate_id", "version"})
_POST_NOTICE = ("Este registro conserva una fuente aportada por la persona; no autentica autoría o "
                "consentimiento y no convierte su contenido en hechos IC, canon ni resultados "
                "confirmados.")
_SEED_NOTICE = ("La persona declara que aporta estas ideas. Son instrucciones de desarrollo, no "
                "hechos IC; OOC y resultados pendientes permanecen separados.")
_PUBLICATION_NOTICE = ("Se registra el texto final como fuente publicada; no se publica nada "
                       "ahora, no se aprueba el borrador si difiere y no se confirman resultados "
                       "que dependan de otros participantes.")


# --- publication boundary (contract only) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    content: str
    content_sha256: str
    destination: str


@dataclass(frozen=True, slots=True)
class PublicationReceipt:
    content_sha256: str
    evidence: object


class PublicationPort(Protocol):
    """The future boundary of publishing. Nothing implements, injects or calls it in 7a."""

    def publish(self, request: PublicationRequest) -> PublicationReceipt: ...


# --- results ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TopicCreateResult:
    topic: LoadedNarrativeTopic
    created: bool


@dataclass(frozen=True, slots=True)
class PostRecordResult:
    topic: LoadedNarrativeTopic
    post: ExternalPost
    created: bool


@dataclass(frozen=True, slots=True)
class SeedImportResult:
    topic: LoadedNarrativeTopic
    seed: HumanSeed
    created: bool


@dataclass(frozen=True, slots=True)
class NarrativeDraftCreateResult:
    topic: LoadedNarrativeTopic
    draft: NarrativeDraftView
    created: bool


@dataclass(frozen=True, slots=True)
class PublicationConfirmResult:
    topic: LoadedNarrativeTopic
    publication: NarrativePublication
    created: bool


# --- queries ----------------------------------------------------------------------------------


def list_topics(instance: LoadedInstance, *,
                character_id: str | None = None) -> tuple[LoadedNarrativeTopic, ...]:
    return tuple(t for t in instance.topics
                 if character_id is None or t.state.header.character_id == character_id)


def get_topic(instance: LoadedInstance, *, topic_id: str) -> LoadedNarrativeTopic:
    for topic in instance.topics:
        if topic.state.topic_id == topic_id:
            return topic
    raise NarrativeError("INVALID_STATE", f"no existe el tema «{topic_id}» en esta instancia")


def list_posts(instance: LoadedInstance, *, topic_id: str) -> tuple[NarrativePostView, ...]:
    return get_topic(instance, topic_id=topic_id).state.replay.posts


def get_post(instance: LoadedInstance, *, topic_id: str, post_id: str) -> NarrativePostView:
    post = get_topic(instance, topic_id=topic_id).state.post(post_id)
    if post is None:
        raise NarrativeError("INVALID_STATE", f"el tema «{topic_id}» no tiene el post {post_id}")
    return post


def list_seeds(instance: LoadedInstance, *, topic_id: str) -> tuple[HumanSeed, ...]:
    return get_topic(instance, topic_id=topic_id).state.seeds


def get_seed(instance: LoadedInstance, *, topic_id: str, seed_id: str,
             version: int) -> HumanSeed:
    seed = get_topic(instance, topic_id=topic_id).state.seed(seed_id, version)
    if seed is None:
        raise NarrativeError("INVALID_STATE", f"el tema «{topic_id}» no tiene la semilla "
                                              f"{seed_id} v{version}")
    return seed


def list_narrative_drafts(instance: LoadedInstance, *,
                          topic_id: str) -> tuple[NarrativeDraftView, ...]:
    return get_topic(instance, topic_id=topic_id).state.replay.draft_views


def get_narrative_draft(instance: LoadedInstance, *, topic_id: str, draft_id: str,
                        version: int) -> NarrativeDraftView:
    view = get_topic(instance, topic_id=topic_id).state.draft_view(draft_id, version)
    if view is None:
        raise NarrativeError("INVALID_STATE", f"el tema «{topic_id}» no tiene el borrador "
                                              f"{draft_id} v{version}")
    return view


# --- mutations --------------------------------------------------------------------------------


def create_topic(instance_root: Path, *, expected_core_root: Path, character_id: str,
                 topic_id: str, title: str) -> TopicCreateResult:
    """Create an empty topic for a character, or return the identical existing one."""
    return _wrap("crear el tema", _create_topic, Path(instance_root), Path(expected_core_root),
                 character_id, topic_id, title)


def record_external_post(instance_root: Path, *, expected_core_root: Path, topic_id: str,
                         input_path: Path, terminal: Terminal) -> PostRecordResult:
    """Record someone else's post as the person transcribed it (barrier A).

    The declared author, locator and text authenticate neither identity nor consent."""
    return _wrap("registrar el post ajeno", _record_external_post, Path(instance_root),
                 Path(expected_core_root), topic_id, Path(input_path), terminal)


def import_human_seed(instance_root: Path, *, expected_core_root: Path, topic_id: str,
                      input_path: Path, terminal: Terminal) -> SeedImportResult:
    """Record the ideas the person declares for the next turn (barrier A); never IC facts."""
    return _wrap("importar la semilla", _import_human_seed, Path(instance_root),
                 Path(expected_core_root), topic_id, Path(input_path), terminal)


def create_narrative_draft(instance_root: Path, *, expected_core_root: Path, topic_id: str,
                           input_path: Path) -> NarrativeDraftCreateResult:
    """Register a complete post developed by the agent from a seed. Not a human action."""
    return _wrap("registrar el borrador", _create_narrative_draft, Path(instance_root),
                 Path(expected_core_root), topic_id, Path(input_path))


def confirm_narrative_publication(instance_root: Path, *, expected_core_root: Path,
                                  topic_id: str, draft_id: str, version: int, input_path: Path,
                                  terminal: Terminal) -> PublicationConfirmResult:
    """After the person published by hand, record the exact final text (barrier A).

    Nothing is published now; an edited text never makes the draft count as published."""
    return _wrap("confirmar la publicación", _confirm_publication, Path(instance_root),
                 Path(expected_core_root), topic_id, draft_id, version, Path(input_path),
                 terminal)


def _wrap(action: str, function, *args):
    try:
        return function(*args)
    except (AssimilationError, InstanceError, WorkspaceError, PersistenceError,
            CharacterError) as exc:
        raise NarrativeError(exc.code, exc.reason) from exc
    except OSError as exc:
        raise NarrativeError("IO", f"error de disco al {action}: {exc}") from exc


def _create_topic(instance_root: Path, core_root: Path, character_id: str, topic_id: str,
                  title: str) -> TopicCreateResult:
    check_narrative_id("topic_id", topic_id)
    check_narrative_id("character_id", character_id)
    check_label("el título", title)
    instance = load_instance(instance_root, expected_core_root=core_root)
    if find_character(instance, character_id) is None:
        raise NarrativeError("INVALID_STATE", f"no existe el personaje «{character_id}»")
    header = TopicHeader(topic_id, character_id, title)
    existing = next((t for t in instance.topics if t.state.topic_id == topic_id), None)
    if existing is not None:
        if existing.state.header == header:
            return TopicCreateResult(existing, False)
        raise NarrativeError("CONFLICT", f"el tema «{topic_id}» ya existe con otro personaje o "
                                         "título")
    state = TopicState(header)
    data = encode_state(encode_topic_content(state), revision=1)
    forum_id = instance.config.forum_id

    def check_staged(staging: Path) -> None:
        revision, content = load_state(staging / TOPIC_STATE)
        if revision != 1 or decode_topic_state(content, forum_id=forum_id, revision=1,
                                               candidate_resolver=_no_candidates,
                                               sheet_check=_no_sheets) != state:
            raise NarrativeError("INVALID_STATE", "el tema preparado no se pudo verificar")

    created = publish_new_folder(
        instance.instance_root / NARRATIVE_DIR / TOPICS_DIR, topic_id, TOPIC_STATE, data,
        instance_root=instance.instance_root, noun="el tema", label=f"«{topic_id}»",
        error=NarrativeError, check_staged=check_staged, lock=_corpus_lock, publish=_publish)
    return TopicCreateResult(_reload(instance, topic_id), created)


def _record_external_post(instance_root: Path, core_root: Path, topic_id: str,
                          input_path: Path, terminal: Terminal) -> PostRecordResult:
    _require_interactive(terminal)
    check_narrative_id("topic_id", topic_id)
    instance = load_instance(instance_root, expected_core_root=core_root)
    topic = get_topic(instance, topic_id=topic_id)
    raw = _read_external(input_path, instance.instance_root, core_root,
                         "el archivo del post ajeno")
    value = _parse_input(raw, input_path, _POST_INPUT_KEYS, "el post ajeno")
    post_id = check_narrative_id("post_id", value["post_id"])
    author = check_label("el autor declarado", value["author_label"])
    locator = check_locator(value["locator"])
    observed = parse_observed_at(value["observed_at"])
    content = _free("el post ajeno", value["content"])
    state = topic.state
    existing = state.post(post_id)
    if existing is not None:
        source = existing.source
        if isinstance(source, ExternalPost) and (
            source.author_label, source.content, source.evidence.locator,
            source.evidence.observed_at.isoformat(),
        ) == (author, content, locator, observed.isoformat()):
            return PostRecordResult(topic, source, False)
        raise NarrativeError("CONFLICT", f"el post {post_id} ya existe en el tema con otro "
                                         "contenido")
    position = len(state.replay.posts) + 1
    _require_free(instance, topic)
    data = content.encode("utf-8")
    receipt = confirm_human_action(
        terminal, phrase_prefix=f"REGISTRAR-POST-AJENO {topic_id} {post_id}",
        prompt=_lines([
            "REGISTRO HUMANO DE POST AJENO",
            f"Foro: {instance.config.forum_id}",
            f"Personaje: {state.header.character_id}",
            f"Tema: {topic_id}",
            f"Post: {post_id}",
            f"Posición: {position}",
            f"Autor declarado: {_json(author)}",
            f"Locator declarado: {_json(locator)}",
            f"Observada en: {observed.isoformat()}",
            f"Contenido SHA-256: {text_sha256(content)}",
            f"Contenido bytes UTF-8: {len(data)}",
        ]) + _block("POST AJENO TRANSCRITO — texto exacto (hasta «Fin del post ajeno.»):",
                    content, "Fin del post ajeno.") + _POST_NOTICE + "\n")
    _require_same_input(input_path, instance, core_root, raw, "el archivo del post ajeno")
    post = make_external_post(topic_id=topic_id, post_id=post_id, position=position,
                              created_revision=state.revision + 1, author_label=author,
                              content=content, locator=locator, observed_at=observed,
                              receipt=receipt)
    reloaded = _append(instance, topic, lambda again, current: replace(
        current.state, external_posts=(*current.state.external_posts, post)))
    return PostRecordResult(reloaded, post, True)


def _import_human_seed(instance_root: Path, core_root: Path, topic_id: str, input_path: Path,
                       terminal: Terminal) -> SeedImportResult:
    _require_interactive(terminal)
    check_narrative_id("topic_id", topic_id)
    instance = load_instance(instance_root, expected_core_root=core_root)
    topic = get_topic(instance, topic_id=topic_id)
    raw = _read_external(input_path, instance.instance_root, core_root,
                         "el archivo de la semilla")
    value = _parse_input(raw, input_path, _SEED_INPUT_KEYS, "la semilla")
    seed_id = check_narrative_id("seed_id", value["seed_id"])
    version = _positive_input("version", value["version"])
    fields = {
        "intent": _free("la intención", value["intent"]),
        "tone": _free("el tono", value["tone"]),
        **{name: _text_list_input(name, value[name])
           for name in ("beats", "details", "ooc_constraints", "pending_outcomes")},
    }
    declared = (fields["intent"], fields["tone"], fields["beats"], fields["details"],
                fields["ooc_constraints"], fields["pending_outcomes"])
    state = topic.state
    existing = state.seed(seed_id, version)
    if existing is not None:
        if seed_semantics(existing) == declared:
            return SeedImportResult(topic, existing, False)
        raise NarrativeError("CONFLICT", f"la semilla {seed_id} v{version} ya existe con otro "
                                         "contenido; crea la versión siguiente")
    previous = state.latest_seed(seed_id)
    expected = 1 if previous is None else previous.version + 1
    if version != expected:
        raise NarrativeError("CONFLICT", f"la siguiente versión de la semilla {seed_id} es la "
                                         f"{expected}, no la {version}")
    context = state.replay.context
    if previous is not None and (seed_semantics(previous), previous.context) == (declared,
                                                                                 context):
        raise NarrativeError("CONFLICT", f"la semilla {seed_id} v{version} repite la anterior")
    _require_free(instance, topic)
    mode = "CONTINUAR" if context else "INICIAR"
    receipt = confirm_human_action(
        terminal, phrase_prefix=f"DECLARAR-SEMILLA {topic_id} {seed_id} v{version}",
        prompt=_lines([
            "DECLARACIÓN HUMANA DE SEMILLA NARRATIVA",
            f"Foro: {instance.config.forum_id}",
            f"Personaje: {state.header.character_id}",
            f"Tema: {topic_id}",
            f"Semilla: {seed_id} v{version}",
            f"Modo: {mode}",
            f"Posts de contexto: {len(context)}",
            f"Contexto SHA-256: {context_sha256(context)}",
            f"Intención: {_json(fields['intent'])}",
            f"Tono: {_json(fields['tone'])}",
            f"Giros: {_json(list(fields['beats']))}",
            f"Detalles: {_json(list(fields['details']))}",
            f"Restricciones OOC: {_json(list(fields['ooc_constraints']))}",
            f"Resultados pendientes: {_json(list(fields['pending_outcomes']))}",
            _SEED_NOTICE,
        ]))
    _require_same_input(input_path, instance, core_root, raw, "el archivo de la semilla")
    seed = make_seed(forum_id=instance.config.forum_id, topic_id=topic_id, seed_id=seed_id,
                     version=version, created_revision=state.revision + 1, context=context,
                     receipt=receipt, **fields)
    reloaded = _append(instance, topic, lambda again, current: replace(
        current.state, seeds=(*current.state.seeds, seed)))
    return SeedImportResult(reloaded, seed, True)


def _create_narrative_draft(instance_root: Path, core_root: Path, topic_id: str,
                            input_path: Path) -> NarrativeDraftCreateResult:
    check_narrative_id("topic_id", topic_id)
    instance = load_instance(instance_root, expected_core_root=core_root)
    topic = get_topic(instance, topic_id=topic_id)
    raw = _read_external(input_path, instance.instance_root, core_root,
                         "el archivo del borrador")
    value = _parse_input(raw, input_path, _DRAFT_INPUT_KEYS, "el borrador")
    draft_id = check_narrative_id("draft_id", value["draft_id"])
    version = _positive_input("version", value["version"])
    seed_id = check_narrative_id("seed_id", value["seed_id"])
    seed_version = _positive_input("seed_version", value["seed_version"])
    seed_sha = _sha_input("seed_sha256", value["seed_sha256"])
    context_sha = _sha_input("context_sha256", value["context_sha256"])
    composition = _sha_input("composition_sha256", value["composition_sha256"])
    sheet_version = _positive_input("sheet_version", value["sheet_version"])
    sheet_sha = _sha_input("sheet_sha256", value["sheet_sha256"])
    citations = value["citations"]
    if not isinstance(citations, list) or not all(
        isinstance(c, dict) and set(c) == _CITATION_INPUT_KEYS for c in citations
    ):
        raise NarrativeError("INVALID_STATE", "cada cita tiene exactamente candidate_id y version")
    wanted = tuple((check_narrative_id("candidate_id", c["candidate_id"]),
                    _positive_input("la versión de la cita", c["version"])) for c in citations)
    if len(set(wanted)) != len(wanted):
        raise NarrativeError("INVALID_STATE", "el borrador repite una cita")
    text = _free("el post", value["publishable_text"])
    lists = {name: _text_list_input(name, value[name])
             for name in ("ooc_notes", "private_notes", "pending_outcomes")}
    state = topic.state
    refs = _resolve(instance, wanted)
    existing = state.draft(draft_id, version)
    semantic = (seed_id, seed_version, seed_sha, composition, sheet_version, sheet_sha, refs,
                text, lists["ooc_notes"], lists["private_notes"], lists["pending_outcomes"])
    if existing is not None:
        if draft_semantics(existing) == semantic and existing.context_sha256 == context_sha:
            return NarrativeDraftCreateResult(topic, state.draft_view(draft_id, version), False)
        raise NarrativeError("CONFLICT", f"el borrador {draft_id} v{version} ya existe con otro "
                                         "contenido; crea la versión siguiente")
    previous = state.latest_draft(draft_id)
    expected = 1 if previous is None else previous.version + 1
    if version != expected:
        raise NarrativeError("CONFLICT", f"la siguiente versión del borrador {draft_id} es la "
                                         f"{expected}, no la {version}")
    record = _new_draft(instance, state, draft_id, version, seed_id, seed_version, seed_sha,
                        context_sha, composition, sheet_version, sheet_sha, refs, text, lists)
    _require_free(instance, topic)
    if previous is not None and (draft_semantics(previous), previous.context) == (
        draft_semantics(record), record.context
    ):
        raise NarrativeError("CONFLICT", f"el borrador {draft_id} v{version} repite el anterior")

    def build(again: LoadedInstance, current: LoadedNarrativeTopic) -> TopicState:
        if _new_draft(again, current.state, draft_id, version, seed_id, seed_version, seed_sha,
                      context_sha, composition, sheet_version, sheet_sha,
                      _resolve(again, wanted), text, lists) != record:
            raise NarrativeError("CONFLICT", "el personaje o el corpus cambiaron mientras se "
                                             "registraba el borrador")
        return replace(current.state, drafts=(*current.state.drafts, record))

    reloaded = _append(instance, topic, build)
    return NarrativeDraftCreateResult(reloaded, reloaded.state.draft_view(draft_id, version), True)


def _new_draft(instance: LoadedInstance, state: TopicState, draft_id: str, version: int,
               seed_id: str, seed_version: int, seed_sha: str, context_sha: str,
               composition: str, sheet_version: int, sheet_sha: str,
               refs: tuple[CorpusCandidateRef, ...], text: str, lists: dict
               ) -> NarrativeDraftRecord:
    seed = state.seed(seed_id, seed_version)
    if seed is None:
        raise NarrativeError("INVALID_STATE", f"no existe la semilla {seed_id} v{seed_version}")
    if seed.seed_sha256 != seed_sha:
        raise NarrativeError("CONFLICT", "seed_sha256 no corresponde a la semilla; consulta "
                                         "«narrative seed show»")
    context = state.replay.context
    if seed.context != context or context_sha256(context) != context_sha:
        raise NarrativeError("CONFLICT", "el contexto del tema ya no es el de la semilla o "
                                         "context_sha256 no es el actual; consulta «narrative "
                                         "topic show»")
    character = find_character(instance, state.header.character_id)
    if character is None:
        raise NarrativeError("INVALID_STATE", "el personaje del tema ya no existe")
    effective = character.state.replay.effective
    if composition != effective.composition_sha256:
        raise NarrativeError("CONFLICT", "composition_sha256 no es la composición efectiva "
                                         "vigente; consulta «character effective show»")
    view = character.state.draft_view(sheet_version)
    response = None if view is None else view.staff_response
    if (view is None or not view.current or view.effective.lifecycle is not DraftLifecycle.ACTIVE
            or response is None or response.review_status is not ReviewStatus.APPROVED):
        raise NarrativeError("CONFLICT", f"la ficha v{sheet_version} no es la vigente, activa y "
                                         "aprobada por el staff")
    if view.record.draft_sha256 != sheet_sha or view.record.composition_sha256 != composition:
        raise NarrativeError("CONFLICT", "sheet_sha256 o la composición no corresponden a la "
                                         "ficha aprobada; consulta «character draft show»")
    sheet = CharacterSheetRef(sheet_version, sheet_sha, composition,
                              response.staff_review_sha256)
    return NarrativeDraftRecord(
        state.topic_id, draft_id, version, state.revision + 1, seed_id, seed_version, seed_sha,
        context, len(context) + 1, character.state_revision, composition, sheet, refs, text,
        lists["ooc_notes"], lists["private_notes"], lists["pending_outcomes"])


def _confirm_publication(instance_root: Path, core_root: Path, topic_id: str, draft_id: str,
                         version: int, input_path: Path,
                         terminal: Terminal) -> PublicationConfirmResult:
    _require_interactive(terminal)
    check_narrative_id("topic_id", topic_id)
    check_narrative_id("draft_id", draft_id)
    _positive_input("la versión del borrador", version)
    instance = load_instance(instance_root, expected_core_root=core_root)
    topic = get_topic(instance, topic_id=topic_id)
    raw = _read_external(input_path, instance.instance_root, core_root,
                         "el archivo de la publicación")
    value = _parse_input(raw, input_path, _PUBLICATION_INPUT_KEYS, "la publicación")
    post_id = check_narrative_id("post_id", value["post_id"])
    draft_sha = _sha_input("draft_sha256", value["draft_sha256"])
    locator = check_locator(value["locator"])
    observed = parse_observed_at(value["observed_at"])
    text = _free("el texto publicado", value["published_text"])
    state = topic.state
    view = get_narrative_draft(instance, topic_id=topic_id, draft_id=draft_id, version=version)
    draft = view.record
    if draft_sha != draft.draft_sha256:
        raise NarrativeError("CONFLICT", f"draft_sha256 no corresponde al borrador {draft_id} "
                                         f"v{version}; consulta «narrative draft show»")
    if view.published is not None:
        published = view.published
        if (published.post_id, published.published_text, published.evidence.locator,
                published.evidence.observed_at.isoformat()) == (post_id, text, locator,
                                                                 observed.isoformat()):
            return PublicationConfirmResult(topic, published, False)
        raise NarrativeError("CONFLICT", f"el borrador {draft_id} v{version} ya tiene otra "
                                         "publicación registrada")
    if draft.context != state.replay.context:
        raise NarrativeError("CONFLICT", "el tema ya no está en el contexto del borrador: "
                                         "registra cada publicación antes de incorporar la "
                                         "respuesta siguiente")
    if state.post(post_id) is not None:
        raise NarrativeError("CONFLICT", f"el post {post_id} ya existe en el tema")
    _require_free(instance, topic)
    character = find_character(instance, state.header.character_id)
    current = character is not None and _sheet_is_current(character, draft)
    final = text.encode("utf-8")
    original = draft.publishable_text.encode("utf-8")
    matches = text == draft.publishable_text
    receipt = confirm_human_action(
        terminal, phrase_prefix=f"CONFIRMAR-PUBLICACION {topic_id} {draft_id} v{version}",
        prompt=_lines([
            "CONFIRMACIÓN HUMANA DE PUBLICACIÓN MANUAL",
            f"Foro: {instance.config.forum_id}",
            f"Personaje: {state.header.character_id}",
            f"Tema: {topic_id}",
            f"Post: {post_id}",
            f"Posición: {draft.target_position}",
            f"Borrador: {draft_id} v{version}",
            f"Borrador SHA-256: {draft.draft_sha256}",
            f"Contexto SHA-256: {draft.context_sha256}",
            f"Composición/ficha vigentes ahora: {'SÍ' if current else 'NO'}",
            f"Locator declarado: {_json(locator)}",
            f"Observada en: {observed.isoformat()}",
            f"Borrador contenido SHA-256: {text_sha256(draft.publishable_text)}",
            f"Borrador bytes UTF-8: {len(original)}",
            f"Texto final SHA-256: {text_sha256(text)}",
            f"Texto final bytes UTF-8: {len(final)}",
            f"Coincidencia exacta: {'SÍ' if matches else 'NO'}",
        ]) + _block("BORRADOR — texto exacto (hasta «Fin del borrador.»):",
                    draft.publishable_text, "Fin del borrador.")
        + _block("TEXTO FINAL PUBLICADO — texto exacto (hasta «Fin del texto final.»):", text,
                 "Fin del texto final.")
        + _lines([f"NO PUBLICAR — OOC: {_json(list(draft.ooc_notes))}",
                  f"NO PUBLICAR — privado: {_json(list(draft.private_notes))}",
                  f"NO PUBLICAR — resultados pendientes: {_json(list(draft.pending_outcomes))}",
                  _PUBLICATION_NOTICE]))
    _require_same_input(input_path, instance, core_root, raw, "el archivo de la publicación")
    publication = make_publication(topic_id=topic_id, post_id=post_id,
                                   publication_revision=state.revision + 1, draft=draft,
                                   published_text=text, locator=locator, observed_at=observed,
                                   receipt=receipt)
    reloaded = _append(instance, topic, lambda again, current_topic: replace(
        current_topic.state, publications=(*current_topic.state.publications, publication)))
    return PublicationConfirmResult(reloaded, publication, True)


# --- helpers ----------------------------------------------------------------------------------


def _append(instance: LoadedInstance, topic: LoadedNarrativeTopic, build) -> LoadedNarrativeTopic:
    """Append one event under the topic lock; any change since `topic` is a CONFLICT."""
    topic_id = topic.state.topic_id

    def prepare() -> bytes:
        again = load_instance(instance.instance_root, expected_core_root=instance.config.core_root)
        current = next((t for t in again.topics if t.state.topic_id == topic_id), None)
        if (current is None or current.state_revision != topic.state_revision
                or current.state != topic.state):
            raise NarrativeError("CONFLICT", "el tema cambió mientras se confirmaba; no se ha "
                                             "guardado nada")
        if again != instance:  # personaje, corpus, expediente u otro tema: lo mostrado ya no vale
            raise NarrativeError("CONFLICT", "la instancia cambió mientras se confirmaba; no se "
                                             "ha guardado nada")
        new_state = build(again, current)
        if new_state.revision != current.state_revision + 1:
            raise NarrativeError("INVALID_STATE", "un cambio debe añadir exactamente un evento")
        return encode_state(encode_topic_content(new_state), revision=new_state.revision)

    root = Path(topic.topic_root)
    append_event(root / TOPIC_STATE, subject="este tema",
                 guard=folder_guard(root, TOPIC_STATE, instance.instance_root, NarrativeError),
                 prepare=prepare, lock=_corpus_lock)
    return _reload(instance, topic_id)


def _require_free(instance: LoadedInstance, topic: LoadedNarrativeTopic) -> None:
    _require_unlocked(Path(topic.topic_root) / TOPIC_STATE, "este tema")
    require_no_update(instance.instance_root)


def _require_same_input(input_path: Path, instance: LoadedInstance, core_root: Path, raw: bytes,
                        label: str) -> None:
    if _read_external(input_path, instance.instance_root, core_root, label) != raw:
        raise NarrativeError("CONFLICT", f"{label} cambió mientras se confirmaba; no se ha "
                                         "guardado nada")


def _reload(instance: LoadedInstance, topic_id: str) -> LoadedNarrativeTopic:
    again = load_instance(instance.instance_root, expected_core_root=instance.config.core_root)
    return get_topic(again, topic_id=topic_id)


def _resolve(instance: LoadedInstance,
             wanted: tuple[tuple[str, int], ...]) -> tuple[CorpusCandidateRef, ...]:
    refs = []
    for candidate_id, version in wanted:
        try:
            candidate = get_approved_candidate(instance, candidate_id=candidate_id,
                                               version=version).candidate
        except InstanceError as exc:
            raise NarrativeError("INVALID_STATE", exc.reason) from exc
        refs.append(CorpusCandidateRef(candidate_id, version, candidate.candidate_sha256))
    return tuple(refs)


def _sheet_is_current(character, draft: NarrativeDraftRecord) -> bool:
    view = character.state.draft_view(draft.sheet.version)
    return (view is not None and view.current
            and view.effective.lifecycle is DraftLifecycle.ACTIVE
            and view.record.draft_sha256 == draft.sheet.draft_sha256
            and character.state.replay.effective.composition_sha256 == draft.composition_sha256)


def _parse_input(raw: bytes, input_path: Path, keys: frozenset, what: str) -> dict:
    value = parse_strict_json(raw, Path(input_path).as_posix())
    if not isinstance(value, dict) or set(value) != keys:
        raise NarrativeError("INVALID_STATE", f"{what} debe tener exactamente las claves "
                                              + ", ".join(sorted(keys)))
    return value


def _free(name: str, value: object) -> str:
    try:
        return _check_free_text(name, value)
    except CharacterError as exc:
        raise NarrativeError("INVALID_STATE", exc.reason) from exc


def _text_list_input(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise NarrativeError("INVALID_STATE", f"{name} debe ser una lista de textos")
    return tuple(_free(name, item) for item in value)


def _positive_input(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise NarrativeError("INVALID_STATE", f"{name} debe ser un entero positivo")
    return value


def _sha_input(name: str, value: object) -> str:
    try:
        return _check_sha256(name, value)
    except CharacterError as exc:
        raise NarrativeError("INVALID_STATE", exc.reason) from exc


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _lines(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


def _block(header: str, text: str, footer: str) -> str:
    return f"{header}\n{text if text.endswith(chr(10)) else text + chr(10)}{footer}\n"


def _no_candidates(candidate_id: str, version: int):
    raise NarrativeError("INVALID_STATE", "un tema nuevo no cita el corpus")


def _no_sheets(*args) -> None:
    raise NarrativeError("INVALID_STATE", "un tema nuevo no cita fichas")
