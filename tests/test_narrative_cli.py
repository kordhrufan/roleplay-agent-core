import json
import re
import subprocess
import sys
import unittest
from unittest import mock

from core.memory.narrative import (
    NarrativeError,
    context_sha256,
    narrative_draft_summary,
    post_summary,
    publication_summary,
    seed_summary,
    text_sha256,
    topic_summary,
)
from core.runtime import cli
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run
from tests.test_narrative_workflow import LOCATOR, OBSERVED, TOPIC, NarrativeCase

JSON_MESSAGES = {
    "post": "los posts ajenos transcritos no admiten --json: ejecuta el comando en tu terminal y "
            "responde a la confirmación",
    "seed": "las declaraciones humanas de semillas narrativas no admiten --json: ejecuta el "
            "comando en tu terminal y responde a la confirmación",
    "publication": "las confirmaciones de publicación manual no admiten --json: ejecuta el "
                   "comando en tu terminal y responde a la confirmación",
}
POST_NOTICE = ("Este registro conserva una fuente aportada por la persona; no autentica autoría o "
               "consentimiento y no convierte su contenido en hechos IC, canon ni resultados "
               "confirmados.\n")
SEED_NOTICE = ("La persona declara que aporta estas ideas. Son instrucciones de desarrollo, no "
               "hechos IC; OOC y resultados pendientes permanecen separados.\n")
PUBLICATION_NOTICE = ("Se registra el texto final como fuente publicada; no se publica nada "
                      "ahora, no se aprueba el borrador si difiere y no se confirman resultados "
                      "que dependan de otros participantes.\n")


class NarrativeCliCase(NarrativeCase):
    def setUp(self):
        super().setUp()
        self.path = str(self.instance)
        self.terminals = []

    def terminal(self, **kwargs):
        def factory():
            terminal = FakeTerminal(**kwargs)
            self.terminals.append(terminal)
            return terminal
        return factory

    def human(self, *argv, terminal=None):
        with mock.patch.object(cli, "_SystemTerminal", terminal or self.terminal()):
            return run(*argv)

    def cli_topic(self, *flags, topic_id=TOPIC, title="Escena en la plaza"):
        return run(*flags, "narrative", "topic", "create", "--instance", self.path,
                   "--character-id", "aria", "--topic-id", topic_id, "--title", title)

    def cli_post(self, *flags, terminal=None, **kwargs):
        path = self.write_json("post.json", self.post_value(**kwargs))
        return self.human(*flags, "narrative", "post", "record", "--instance", self.path,
                          "--topic-id", TOPIC, "--input", str(path), terminal=terminal)

    def cli_seed(self, *flags, terminal=None, **kwargs):
        path = self.write_json("semilla.json", self.seed_value(**kwargs))
        return self.human(*flags, "narrative", "seed", "import", "--instance", self.path,
                          "--topic-id", TOPIC, "--input", str(path), terminal=terminal)

    def cli_draft(self, *flags, **kwargs):
        path = self.write_json("borrador.json", self.draft_value(**kwargs))
        return run(*flags, "narrative", "draft", "create", "--instance", self.path,
                   "--topic-id", TOPIC, "--input", str(path))

    def cli_confirm(self, *flags, terminal=None, draft_id="turno-1", version="1", **kwargs):
        path = self.write_json("publicacion.json",
                               self.publication_value(draft_id=draft_id, version=int(version),
                                                      **kwargs))
        return self.human(*flags, "narrative", "publication", "confirm", "--instance", self.path,
                          "--topic-id", TOPIC, "--draft-id", draft_id, "--version", version,
                          "--input", str(path), terminal=terminal)

    # --- expected lines ---

    def topic_line(self):
        topic = self.topic()
        state = topic.state
        return (f"{TOPIC} | personaje=aria | posts={len(state.replay.posts)} | "
                f"semillas={len(state.seeds)} | borradores={len(state.drafts)} | "
                f"publicaciones={len(state.publications)} | "
                f"contexto={context_sha256(state.replay.context)} | "
                f"revisión={topic.state_revision} | título={json.dumps(state.header.title, ensure_ascii=False)}")

    def post_line(self, post_id):
        post = self.state().post(post_id)
        source = post.source
        return (f"p{post.position} | {post.author.value} | {post_id} | "
                f"sha256={text_sha256(post.content)} | bytes={len(post.content.encode())} | "
                f"locator={json.dumps(source.evidence.locator, ensure_ascii=False)} | "
                f"observada={source.evidence.observed_at.isoformat()}")

    def seed_line(self, seed_id="turno-1", version=1):
        seed = self.state().seed(seed_id, version)
        return (f"{seed_id} v{version} | {seed.mode.value} | sha256={seed.seed_sha256} | "
                f"contexto={context_sha256(seed.context)} | posts={len(seed.context)} | "
                f"pendientes={len(seed.pending_outcomes)}")

    def draft_line(self, draft_id="turno-1", version=1):
        view = self.state().draft_view(draft_id, version)
        record = view.record
        return (f"{draft_id} v{version} | {view.lifecycle.value} | "
                f"publicación={view.publication.value} | posición={record.target_position} | "
                f"semilla={record.seed_id}:v{record.seed_version}:{record.seed_sha256} | "
                f"composición={record.composition_sha256} | "
                f"ficha=v{record.sheet.version}:{record.sheet.draft_sha256} | "
                f"sha256={record.draft_sha256} | bytes={record.utf8_size} | "
                f"citas={len(record.citations)} | pendientes={len(record.pending_outcomes)}")


def with_nonce_removed(output, prefix):
    match = re.fullmatch(rf"(.*)Escribe exactamente: {re.escape(prefix)} ([A-Z0-9]+)\n> ",
                         output, re.S)
    assert match, output[-200:]
    return match.group(1)


class ParserTest(NarrativeCliCase):
    def test_every_argument_is_required_and_nothing_publishes(self):
        full = {
            ("topic", "create"): ["--instance", "x", "--character-id", "a", "--topic-id", "t",
                                  "--title", "T"],
            ("topic", "show"): ["--instance", "x", "--topic-id", "t"],
            ("post", "record"): ["--instance", "x", "--topic-id", "t", "--input", "x"],
            ("post", "list"): ["--instance", "x", "--topic-id", "t"],
            ("post", "show"): ["--instance", "x", "--topic-id", "t", "--post-id", "p"],
            ("seed", "import"): ["--instance", "x", "--topic-id", "t", "--input", "x"],
            ("seed", "list"): ["--instance", "x", "--topic-id", "t"],
            ("seed", "show"): ["--instance", "x", "--topic-id", "t", "--seed-id", "s",
                               "--version", "1"],
            ("draft", "create"): ["--instance", "x", "--topic-id", "t", "--input", "x"],
            ("draft", "list"): ["--instance", "x", "--topic-id", "t"],
            ("draft", "show"): ["--instance", "x", "--topic-id", "t", "--draft-id", "d",
                                "--version", "1"],
            ("publication", "confirm"): ["--instance", "x", "--topic-id", "t", "--draft-id", "d",
                                         "--version", "1", "--input", "x"],
        }
        for (group, action), args in full.items():
            for index in range(0, len(args), 2):
                argv = ["narrative", group, action, *args[:index], *args[index + 2:]]
                with self.subTest(argv=argv):
                    self.assertEqual(run(*argv)[0], 2)
        self.assertEqual(run("narrative", "topic", "list")[0], 2)
        for argv in (["narrative", "publish"], ["narrative", "send"], ["narrative", "export"],
                     ["narrative", "draft", "publish"], ["narrative", "draft", "export"],
                     ["narrative", "publication", "publish"], ["narrative", "publication", "send"],
                     ["narrative", "post", "send"], ["narrative", "outbox"],
                     ["narrative", "seed", "show", *full[("seed", "show")][:-1], "0"],
                     ["narrative", "draft", "show", *full[("draft", "show")][:-1], "latest"],
                     ["narrative", "publication", "confirm", *full[("publication", "confirm")],
                      "--yes"],
                     ["narrative", "post", "record", *full[("post", "record")], "--nonce", "X"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)
        parser_source = (ROOT / "core" / "runtime" / "cli.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r'add_parser\("(publish|send|export)', parser_source))


class TopicCliTest(NarrativeCliCase):
    def test_create_list_show_text_and_json(self):
        code, out, _ = self.cli_topic()
        self.assertEqual((code, out), (0, f"Tema creado: {self.topic_line()}\n"
                                          "Revisión del tema: 1.\n"))
        code, out, _ = self.cli_topic()
        self.assertEqual((code, out), (0, f"Tema ya existente: {self.topic_line()}\n"
                                          "Revisión del tema: 1.\n"))
        code, out, _ = self.cli_topic("--json")
        self.assertEqual((code, json.loads(out)), (0, {
            "ok": True, "action": "narrative.topic.create", "created": False,
            "instance": self.path, "state_revision": 1, "topic_id": TOPIC,
            "topic": topic_summary(self.state())}))
        self.assertEqual(self.cli_topic(title="Otro")[0], 4)
        self.assertEqual(run("narrative", "topic", "list", "--instance", self.path),
                         (0, self.topic_line() + "\n", ""))
        self.assertEqual(run("narrative", "topic", "list", "--instance", self.path,
                             "--character-id", "otro"),
                         (0, "No hay temas para «otro».\n", ""))
        code, out, _ = run("--json", "narrative", "topic", "list", "--instance", self.path)
        self.assertEqual(json.loads(out), {"ok": True, "action": "narrative.topic.list",
                                           "instance": self.path,
                                           "topics": [topic_summary(self.state())]})
        self.assertEqual(run("narrative", "topic", "show", "--instance", self.path, "--topic-id",
                             TOPIC), (0, f"{self.topic_line()}\nNo hay posts para «{TOPIC}».\n",
                                      ""))
        self.record_post(content="Sin salto final")
        code, out, _ = run("narrative", "topic", "show", "--instance", self.path, "--topic-id",
                           TOPIC)
        self.assertEqual(out, f"{self.topic_line()}\n{self.post_line('respuesta-1')}\n"
                              "Post p1 (exacto, hasta «Fin del post p1.»):\nSin salto final\n"
                              "Fin del post p1.\n")
        code, out, _ = run("--json", "narrative", "topic", "show", "--instance", self.path,
                           "--topic-id", TOPIC)
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "narrative.topic.show", "instance": self.path,
            "posts": [post_summary(self.state().post("respuesta-1"))], "state_revision": 2,
            "topic": topic_summary(self.state()), "topic_id": TOPIC})
        receipt = json.loads(out)["posts"][0]["receipt"]
        self.assertEqual(sorted(receipt), ["confirmation_sha256", "method"])

    def test_error_codes(self):
        self.assertEqual(self.cli_topic(topic_id="Mal")[0], 3)
        code, out, _ = run("--json", "narrative", "topic", "show", "--instance", self.path,
                           "--topic-id", "no-existe")
        self.assertEqual((code, json.loads(out)["code"]), (3, "INVALID_STATE"))
        with mock.patch.object(cli, "create_topic",
                               side_effect=NarrativeError("IO", "disco")):
            code, out, _ = self.cli_topic("--json")
        self.assertEqual((code, json.loads(out)),
                         (5, {"ok": False, "code": "IO", "message": "disco"}))
        code, _, err = run("narrative", "topic", "list", "--instance", str(self.root / "nada"))
        self.assertEqual(code, 3)
        self.assertTrue(err.startswith("Error (INVALID_STATE): "))


class HumanActionsCliTest(NarrativeCliCase):
    def test_json_is_rejected_before_any_prompt(self):
        self.ready()
        before = self.snapshot()
        for name, action in (("post", self.cli_post), ("seed", self.cli_seed),
                             ("publication", self.cli_confirm)):
            with self.subTest(name=name):
                code, out, _ = action("--json")
                self.assertEqual((code, json.loads(out)), (3, {
                    "ok": False, "code": "INVALID_STATE", "message": JSON_MESSAGES[name]}))
        self.assertEqual((self.terminals, self.snapshot()), ([], before))

    def test_real_terminal_paths_need_a_tty(self):
        self.ready()
        before = self.snapshot()
        path = self.write_json("post.json", self.post_value())
        argv = ["narrative", "post", "record", "--instance", self.path, "--topic-id", TOPIC,
                "--input", str(path)]
        code, out, err = run(*argv, stdin="REGISTRAR-POST-AJENO escena respuesta-1 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("terminal interactiva", err)
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(b"REGISTRAR-POST-AJENO", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_external_post_prompt_and_outputs(self):
        self.new_topic()
        content = "Línea «uno»\r\nsin final"
        code, out, _ = self.cli_post(content=content)
        prompt = with_nonce_removed(self.terminals[-1].output,
                                    "REGISTRAR-POST-AJENO escena respuesta-1")
        self.assertEqual(prompt, (
            "REGISTRO HUMANO DE POST AJENO\n"
            "Foro: foro-neutral\n"
            "Personaje: aria\n"
            "Tema: escena\n"
            "Post: respuesta-1\n"
            "Posición: 1\n"
            "Autor declarado: \"otro participante\"\n"
            f"Locator declarado: {json.dumps(LOCATOR)}\n"
            f"Observada en: {OBSERVED}\n"
            f"Contenido SHA-256: {text_sha256(content)}\n"
            f"Contenido bytes UTF-8: {len(content.encode())}\n"
            "POST AJENO TRANSCRITO — texto exacto (hasta «Fin del post ajeno.»):\n"
            f"{content}\n"
            "Fin del post ajeno.\n" + POST_NOTICE))
        self.assertEqual((code, out), (0, f"Post ajeno registrado: {self.post_line('respuesta-1')}"
                                          "\nRevisión del tema: 2.\n"))
        code, out, _ = self.cli_post(content=content)
        self.assertEqual((code, out), (0, f"Post ajeno ya existente: "
                                          f"{self.post_line('respuesta-1')}\n"
                                          "Revisión del tema: 2.\n"))
        self.assertEqual(self.terminals[-1].reads, 0)
        self.assertEqual(self.cli_post(content="Otro")[0], 4)
        self.assertEqual(run("narrative", "post", "list", "--instance", self.path, "--topic-id",
                             TOPIC), (0, self.post_line("respuesta-1") + "\n", ""))
        post = self.state().post("respuesta-1")
        code, out, _ = run("narrative", "post", "show", "--instance", self.path, "--topic-id",
                           TOPIC, "--post-id", "respuesta-1")
        self.assertEqual(out, (f"{self.post_line('respuesta-1')}\n"
                               "Autor declarado: \"otro participante\"\n"
                               f"Evidencia: external-post:escena:respuesta-1 | "
                               f"sha256={post.source.evidence.sha256}\n"
                               "Texto (exacto, hasta «Fin del texto.»):\n"
                               f"{content}\nFin del texto.\n"))
        code, out, _ = run("--json", "narrative", "post", "show", "--instance", self.path,
                           "--topic-id", TOPIC, "--post-id", "respuesta-1")
        self.assertEqual(json.loads(out), {"ok": True, "action": "narrative.post.show",
                                           "instance": self.path, "post": post_summary(post),
                                           "state_revision": 2, "topic_id": TOPIC})
        code, out, _ = run("--json", "narrative", "post", "list", "--instance", self.path,
                           "--topic-id", TOPIC)
        self.assertEqual(json.loads(out)["posts"], [post_summary(post)])
        self.assertEqual(run("narrative", "post", "show", "--instance", self.path, "--topic-id",
                             TOPIC, "--post-id", "otro")[0], 3)

    def test_seed_prompt_with_empty_and_many_items(self):
        self.new_topic()
        code, out, _ = self.cli_seed(beats=(), details=("Uno", "Dos «b»"), ooc_constraints=(),
                                     pending_outcomes=())
        prompt = with_nonce_removed(self.terminals[-1].output, "DECLARAR-SEMILLA escena turno-1 v1")
        self.assertEqual(prompt, (
            "DECLARACIÓN HUMANA DE SEMILLA NARRATIVA\n"
            "Foro: foro-neutral\n"
            "Personaje: aria\n"
            "Tema: escena\n"
            "Semilla: turno-1 v1\n"
            "Modo: INICIAR\n"
            "Posts de contexto: 0\n"
            f"Contexto SHA-256: {context_sha256(())}\n"
            "Intención: \"Presentarse en la plaza\"\n"
            "Tono: \"Sereno\"\n"
            "Giros: []\n"
            "Detalles: [\"Uno\", \"Dos «b»\"]\n"
            "Restricciones OOC: []\n"
            "Resultados pendientes: []\n" + SEED_NOTICE))
        self.assertEqual((code, out), (0, f"Semilla importada: {self.seed_line()}\n"
                                          "Revisión del tema: 2.\n"))
        self.record_post()
        self.cli_seed(version=2, intent="Responder\ncon calma")
        prompt = with_nonce_removed(self.terminals[-1].output, "DECLARAR-SEMILLA escena turno-1 v2")
        self.assertIn("Modo: CONTINUAR\nPosts de contexto: 1\n", prompt)
        self.assertIn("Intención: \"Responder\\ncon calma\"\n", prompt)
        self.assertIn("Giros: [\"Llega al atardecer\"]\n", prompt)
        self.assertEqual(run("narrative", "seed", "list", "--instance", self.path, "--topic-id",
                             TOPIC), (0, f"{self.seed_line()}\n{self.seed_line(version=2)}\n", ""))
        code, out, _ = run("narrative", "seed", "show", "--instance", self.path, "--topic-id",
                           TOPIC, "--seed-id", "turno-1", "--version", "2")
        self.assertEqual(out, (f"{self.seed_line(version=2)}\n"
                               "Intención: \"Responder\\ncon calma\"\nTono: \"Sereno\"\n"
                               "Giros: [\"Llega al atardecer\"]\nDetalles: [\"Lleva su capa\"]\n"
                               "Restricciones OOC: [\"No decidir por otros\"]\n"
                               "Resultados pendientes: [\"Si el guardia la deja pasar\"]\n"))
        code, out, _ = run("--json", "narrative", "seed", "show", "--instance", self.path,
                           "--topic-id", TOPIC, "--seed-id", "turno-1", "--version", "2")
        self.assertEqual(json.loads(out), {"ok": True, "action": "narrative.seed.show",
                                           "instance": self.path,
                                           "seed": seed_summary(self.state().seed("turno-1", 2)),
                                           "state_revision": 4, "topic_id": TOPIC})
        self.assertEqual(sorted(json.loads(out)["seed"]["receipt"]),
                         ["confirmation_sha256", "method"])

    def test_wrong_phrase_eof_and_ctrl_c_through_the_cli(self):
        self.new_topic()
        before = self.snapshot()
        for kwargs in ({"transform": lambda p: p.lower() + "\n"}, {"transform": lambda p: None},
                       {"transform": lambda p: " " + p + "\n"}):
            with self.subTest(kwargs=kwargs):
                code, out, err = self.cli_seed(terminal=self.terminal(**kwargs))
                self.assertEqual((code, out), (3, ""))
                self.assertTrue(err.startswith("Error (INVALID_STATE): "))
        def interrupt():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.cli_seed(terminal=self.terminal(on_read=interrupt))
        self.assertEqual(self.snapshot(), before)


class DraftAndPublicationCliTest(NarrativeCliCase):
    def test_draft_create_list_show_with_separate_channels(self):
        self.new_topic()
        self.seed()
        code, out, _ = self.cli_draft(text="Aria cruza la plaza.", citations=(("normas", 3),
                                                                               ("duda", 1)))
        self.assertEqual((code, out), (0, f"Borrador creado: {self.draft_line()}\n"
                                          "Revisión del tema: 3.\n"))
        code, out, _ = self.cli_draft("--json", text="Aria cruza la plaza.",
                                      citations=(("normas", 3), ("duda", 1)))
        self.assertEqual((code, json.loads(out)), (0, {
            "ok": True, "action": "narrative.draft.create", "created": False,
            "draft": narrative_draft_summary(self.state().draft_view("turno-1", 1)),
            "instance": self.path, "state_revision": 3, "topic_id": TOPIC}))
        self.assertEqual(self.cli_draft(text="Otro")[0], 4)
        self.assertEqual(self.cli_draft(draft_id="x", citations=(("idea", 1),))[0], 3)
        record = self.state().draft("turno-1", 1)
        code, out, _ = run("narrative", "draft", "show", "--instance", self.path, "--topic-id",
                           TOPIC, "--draft-id", "turno-1", "--version", "1")
        corpus = {c.key: c.candidate_sha256 for c in record.citations}
        expected = (f"{self.draft_line()}\n"
                    f"Contexto: sha256={context_sha256(())} | posts=0\n"
                    f"Ficha: v1 | sha256={record.sheet.draft_sha256} | "
                    f"staff={record.sheet.staff_review_sha256} | revisión del personaje=3\n"
                    f"Cita: normas v3 | sha256={corpus[('normas', 3)]}\n"
                    f"Cita: duda v1 | sha256={corpus[('duda', 1)]}\n"
                    "Publicación: ninguna.\n"
                    "POST PARA COPIA MANUAL (no acredita publicación, hasta «Fin del post.»):\n"
                    "Aria cruza la plaza.\n"
                    "Fin del post.\n"
                    "NO PUBLICAR — OOC: [\"Nota OOC\"]\n"
                    "NO PUBLICAR — privado: [\"Pienso que...\"]\n"
                    "NO PUBLICAR — resultados pendientes: [\"Respuesta del guardia\"]\n")
        self.assertEqual((code, out), (0, expected))
        copy_block = out.split("hasta «Fin del post.»):\n")[1].split("Fin del post.\n")[0]
        for private in ("Nota OOC", "Pienso que", "Respuesta del guardia"):
            self.assertNotIn(private, copy_block)
        self.assertEqual(run("narrative", "draft", "list", "--instance", self.path, "--topic-id",
                             TOPIC), (0, self.draft_line() + "\n", ""))
        code, out, _ = run("--json", "narrative", "draft", "show", "--instance", self.path,
                           "--topic-id", TOPIC, "--draft-id", "turno-1", "--version", "1")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "narrative.draft.show",
            "draft": narrative_draft_summary(self.state().draft_view("turno-1", 1)),
            "instance": self.path, "state_revision": 3, "topic_id": TOPIC})
        self.assertNotIn("facts", json.loads(out)["draft"])
        self.assertNotIn("canon", json.loads(out)["draft"])

    def test_publication_prompt_and_outputs(self):
        self.ready()
        record = self.state().draft("turno-1", 1)
        final = "Aria cruza la plaza, despacio."
        code, out, _ = self.cli_confirm(text=final)
        prompt = with_nonce_removed(self.terminals[-1].output,
                                    "CONFIRMAR-PUBLICACION escena turno-1 v1")
        self.assertEqual(prompt, (
            "CONFIRMACIÓN HUMANA DE PUBLICACIÓN MANUAL\n"
            "Foro: foro-neutral\n"
            "Personaje: aria\n"
            "Tema: escena\n"
            "Post: post-propio-1\n"
            "Posición: 1\n"
            "Borrador: turno-1 v1\n"
            f"Borrador SHA-256: {record.draft_sha256}\n"
            f"Contexto SHA-256: {record.context_sha256}\n"
            "Composición/ficha vigentes ahora: SÍ\n"
            f"Locator declarado: {json.dumps(LOCATOR + '2')}\n"
            "Observada en: 2026-10-14T20:15:00+02:00\n"
            f"Borrador contenido SHA-256: {text_sha256(record.publishable_text)}\n"
            f"Borrador bytes UTF-8: {len(record.publishable_text.encode())}\n"
            f"Texto final SHA-256: {text_sha256(final)}\n"
            f"Texto final bytes UTF-8: {len(final.encode())}\n"
            "Coincidencia exacta: NO\n"
            "BORRADOR — texto exacto (hasta «Fin del borrador.»):\n"
            "Aria cruza la plaza.\n"
            "Fin del borrador.\n"
            "TEXTO FINAL PUBLICADO — texto exacto (hasta «Fin del texto final.»):\n"
            f"{final}\n"
            "Fin del texto final.\n"
            "NO PUBLICAR — OOC: [\"Nota OOC\"]\n"
            "NO PUBLICAR — privado: [\"Pienso que...\"]\n"
            "NO PUBLICAR — resultados pendientes: [\"Respuesta del guardia\"]\n"
            + PUBLICATION_NOTICE))
        expected_tail = (f"{self.post_line('post-propio-1')}\n{self.draft_line()}\n"
                         "Revisión del tema: 4.\n")
        self.assertEqual((code, out), (0, "Publicación confirmada: " + expected_tail))
        self.assertIn("publicación=EDITED", out)
        code, out, _ = self.cli_confirm(text=final)
        self.assertEqual((code, out), (0, "Publicación ya confirmada: " + expected_tail))
        self.assertEqual(self.cli_confirm(text="Otra")[0], 4)
        publication = self.state().publications[0]
        code, out, _ = run("--json", "narrative", "post", "show", "--instance", self.path,
                           "--topic-id", TOPIC, "--post-id", "post-propio-1")
        self.assertEqual(json.loads(out)["post"], {**publication_summary(publication),
                                                   "author": "SELF"})
        code, out, _ = run("narrative", "post", "show", "--instance", self.path, "--topic-id",
                           TOPIC, "--post-id", "post-propio-1")
        self.assertIn(f"Borrador: turno-1 v1 | sha256={record.draft_sha256} | "
                      "coincidencia exacta=NO\n", out)
        self.assertIn(f"\n{final}\nFin del texto.\n", out)

    def test_empty_lists(self):
        self.new_topic()
        for group, word in (("post", "posts"), ("seed", "semillas"), ("draft", "borradores")):
            with self.subTest(group=group):
                self.assertEqual(run("narrative", group, "list", "--instance", self.path,
                                     "--topic-id", TOPIC),
                                 (0, f"No hay {word} para «{TOPIC}».\n", ""))
                code, out, _ = run("--json", "narrative", group, "list", "--instance", self.path,
                                   "--topic-id", TOPIC)
                key = {"post": "posts", "seed": "seeds", "draft": "drafts"}[group]
                self.assertEqual(json.loads(out), {"ok": True,
                                                   "action": f"narrative.{group}.list",
                                                   "instance": self.path, key: [],
                                                   "state_revision": 1, "topic_id": TOPIC})


if __name__ == "__main__":
    unittest.main()
