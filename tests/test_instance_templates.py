import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from core.runtime import cli
from core.runtime.instance import (
    AGENTS_TEMPLATE,
    AGENTS_V2_TEMPLATE,
    CLAUDE_TEMPLATE,
    CLAUDE_V2_TEMPLATE,
    COMMON_BEGIN,
    COMMON_END,
    INSTANCE_TEMPLATE,
    POLICY_TEMPLATE,
    POLICY_V2_TEMPLATE,
    create_instance,
    render_instructions,
)
from core.runtime.persistence import parse_strict_json
from tests.instance_support import ROOT, closed_workspace

TEMPLATES = (INSTANCE_TEMPLATE, POLICY_TEMPLATE, AGENTS_TEMPLATE, CLAUDE_TEMPLATE)


def common_block(text: str) -> str:
    begin, end = text.index(COMMON_BEGIN) + len(COMMON_BEGIN), text.index(COMMON_END)
    return text[begin:end]


class TemplateFileTest(unittest.TestCase):
    def test_exact_contents(self):
        from tests import expected_instance_templates as expected
        for template, content in ((INSTANCE_TEMPLATE, expected.EXPECTED_INSTANCE_JSON),
                                  (POLICY_TEMPLATE, expected.EXPECTED_POLICY),
                                  (AGENTS_TEMPLATE, expected.EXPECTED_AGENTS),
                                  (CLAUDE_TEMPLATE, expected.EXPECTED_CLAUDE)):
            with self.subTest(template=template.name):
                self.assertEqual(template.read_bytes(), content.encode("utf-8"))

    def test_encoding_and_line_ends(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                raw = template.read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))
                raw.decode("utf-8")

    def test_policy_is_the_fixed_invariant_block(self):
        policy = POLICY_TEMPLATE.read_text(encoding="utf-8")
        self.assertTrue(policy.startswith("## Invariantes obligatorias\n\n"))
        self.assertEqual(policy.count("\n- "), 5)
        for fragment in ("No ejecutes nunca comandos de decisión humana",
                         "`assimilation candidate approve`", "`assimilation close`",
                         "BORRADOR, APROBADO, PUBLICADO y CANON son estados distintos",
                         "No existe comando de publicación",
                         "No edites directamente estados JSON gestionados"):
            self.assertIn(fragment, policy)

    def test_instruction_templates_differ_only_outside_the_common_block(self):
        agents = AGENTS_TEMPLATE.read_text(encoding="utf-8")
        claude = CLAUDE_TEMPLATE.read_text(encoding="utf-8")
        for text in (agents, claude):
            self.assertEqual(text.count(COMMON_BEGIN), 1)
            self.assertEqual(text.count(COMMON_END), 1)
            self.assertEqual(common_block(text), "$common_policy")
        self.assertEqual(agents.replace("Este `AGENTS.md` rige esta carpeta y todas sus "
                                        "subcarpetas para Codex. Un `AGENTS.md` más específico "
                                        "puede concretar trabajo futuro",
                                        "X"),
                         claude.replace("Este `CLAUDE.md` da a Claude las instrucciones de "
                                        "proyecto para esta carpeta y todas sus subcarpetas. "
                                        "Instrucciones más específicas pueden concretar trabajo "
                                        "futuro", "X"))


class RenderedInstructionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        workspace = closed_workspace(cls.root)
        cls.output = cls.root / "instancia con 'comilla' y ñ"
        cls.instance = create_instance(workspace, output=cls.output, core_root=ROOT).instance

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def rendered(self):
        return {name: (self.output / name).read_text(encoding="utf-8")
                for name in ("AGENTS.md", "CLAUDE.md")}

    def test_common_block_is_the_policy_byte_for_byte(self):
        policy = POLICY_TEMPLATE.read_text(encoding="utf-8")
        for name, text in self.rendered().items():
            with self.subTest(name=name):
                self.assertEqual(text.count(COMMON_BEGIN), 1)
                self.assertEqual(common_block(text), policy)
                self.assertTrue(common_block(text).endswith("\n"))

    def test_rendered_files_are_exact(self):
        from tests import expected_instance_templates as expected
        policy = expected.EXPECTED_POLICY
        root_ps = str(ROOT).replace("'", "''")
        instance_ps = str(self.output).replace("'", "''")
        for name, template in (("AGENTS.md", expected.EXPECTED_AGENTS),
                               ("CLAUDE.md", expected.EXPECTED_CLAUDE)):
            with self.subTest(name=name):
                wanted = (template.replace("$display_name", "Foro neutral de prueba")
                          .replace("$forum_id", "foro-neutral")
                          .replace("$common_policy", policy)
                          .replace("$core_root_ps", root_ps)
                          .replace("$instance_root_ps", instance_ps))
                self.assertEqual((self.output / name).read_bytes(), wanted.encode("utf-8"))

    def test_render_function_matches_files(self):
        config = self.instance.config
        self.assertEqual(render_instructions(AGENTS_TEMPLATE, config),
                         (self.output / "AGENTS.md").read_bytes())
        self.assertEqual(render_instructions(CLAUDE_TEMPLATE, config),
                         (self.output / "CLAUDE.md").read_bytes())

    def test_powershell_paths_are_quoted_and_escaped(self):
        quoted_instance = "'" + str(self.output).replace("'", "''") + "'"
        for name, text in self.rendered().items():
            with self.subTest(name=name):
                self.assertIn(f"Push-Location '{ROOT}'", text)
                self.assertEqual(text.count(f"--instance {quoted_instance}"), 3)
                for line in text.splitlines():
                    if line.startswith(("Push-Location", "py -3.11")):
                        # every single-quoted literal is balanced once '' is collapsed
                        self.assertEqual(line.replace("''", "").count("'") % 2, 0, line)

    def test_names_and_content(self):
        for name, text in self.rendered().items():
            with self.subTest(name=name):
                self.assertIn("«Foro neutral de prueba» (ID «foro-neutral»)", text)
                self.assertNotIn("$", text.replace("$env", ""))
                for forbidden in ("specialists", "--nonce", "--yes", "publish", "Nozomu",
                                  "Naruto", "Jcink"):
                    self.assertNotIn(forbidden, text)
                commands = re.findall(r"core\.runtime\.cli (\w+ \w+(?: \w+)?)", text)
                self.assertEqual(sorted(set(commands)),
                                 ["instance corpus list", "instance corpus show", "instance status"])

    def test_instance_template_renders_to_strict_json(self):
        raw = (self.output / "instance.json").read_bytes()
        data = parse_strict_json(raw, "instance.json")
        self.assertEqual(data["kind"], "forum-roleplay-instance")
        self.assertEqual(data["instance_root"], str(self.output))
        self.assertEqual(data["packages"], [])


V2_TEMPLATES = (POLICY_V2_TEMPLATE, AGENTS_V2_TEMPLATE, CLAUDE_V2_TEMPLATE)
# 7b: every command the v2 instructions may name, as (group..., action).
REAL_COMMANDS = {
    ("instance", "status"), ("instance", "corpus", "list"), ("instance", "corpus", "show"),
    ("character", "concept", "import"), ("character", "concept", "list"),
    ("character", "concept", "show"), ("character", "effective", "show"),
    ("character", "proposal", "add"), ("character", "proposal", "list"),
    ("character", "proposal", "show"), ("character", "proposal", "approve"),
    ("character", "proposal", "reject"), ("character", "draft", "create"),
    ("character", "draft", "list"), ("character", "draft", "show"),
    ("character", "staff", "record"), ("narrative", "topic", "create"),
    ("narrative", "topic", "list"), ("narrative", "topic", "show"),
    ("narrative", "post", "record"), ("narrative", "post", "list"),
    ("narrative", "post", "show"), ("narrative", "seed", "import"),
    ("narrative", "seed", "list"), ("narrative", "seed", "show"),
    ("narrative", "draft", "create"), ("narrative", "draft", "list"),
    ("narrative", "draft", "show"), ("narrative", "publication", "confirm"),
}
HUMAN_COMMANDS = {
    ("character", "concept", "import"), ("character", "proposal", "approve"),
    ("character", "proposal", "reject"), ("character", "staff", "record"),
    ("narrative", "post", "record"), ("narrative", "seed", "import"),
    ("narrative", "publication", "confirm"),
}
PLACEHOLDERS = {"'$instance_root_ps'": "INSTANCIA", "'ID_PERSONAJE'": "personaje",
                "'ID_TEMA'": "tema", "'ID_OBJETO'": "objeto", "'HASH'": "a" * 64,
                "'RUTA_EXTERNA'": "entrada.json", "'TÍTULO'": "Título", " N": " 1",
                "'APPROVED'": "APPROVED"}


def command_lines(text: str) -> list[str]:
    prefix = "py -3.11 -B -m core.runtime.cli "
    return [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]


def command_key(argv: list[str]) -> tuple[str, ...]:
    return tuple(argv[:3]) if argv[0] in ("character", "narrative") or argv[1] == "corpus" \
        else tuple(argv[:2])


class TemplateV2FileTest(unittest.TestCase):
    def test_exact_contents_encoding_and_line_ends(self):
        from tests import expected_instance_templates as expected
        for template, content in ((POLICY_V2_TEMPLATE, expected.EXPECTED_POLICY_V2),
                                  (AGENTS_V2_TEMPLATE, expected.EXPECTED_AGENTS_V2),
                                  (CLAUDE_V2_TEMPLATE, expected.EXPECTED_CLAUDE_V2)):
            with self.subTest(template=template.name):
                raw = template.read_bytes()
                self.assertEqual(raw, content.encode("utf-8"))
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))

    def test_v1_templates_are_unchanged(self):
        from tests import expected_instance_templates as expected
        for template, content in ((POLICY_TEMPLATE, expected.EXPECTED_POLICY),
                                  (AGENTS_TEMPLATE, expected.EXPECTED_AGENTS),
                                  (CLAUDE_TEMPLATE, expected.EXPECTED_CLAUDE)):
            self.assertEqual(template.read_bytes(), content.encode("utf-8"))

    def test_policy_v2_states_the_ten_invariants_in_order(self):
        policy = POLICY_V2_TEMPLATE.read_text(encoding="utf-8")
        self.assertTrue(policy.startswith("## Invariantes obligatorias\n\n"))
        items = re.findall(r"^(\d+)\. ", policy, re.M)
        self.assertEqual(items, [str(n) for n in range(1, 11)])
        for command in ("assimilation candidate approve", "assimilation candidate reject",
                        "assimilation close", "instance update", "instance instructions update",
                        "character concept import", "character proposal approve",
                        "character proposal reject", "character staff record",
                        "narrative post record", "narrative seed import",
                        "narrative publication confirm", "character proposal add",
                        "character draft create", "narrative topic create",
                        "narrative draft create"):
            self.assertIn(f"`{command}`", policy)
        for fragment in ("UNCERTAINTY", "acuerdo con el staff", "no inventes permisos",
                         "Discord", "un locator es solo texto de evidencia",
                         "`publishable_text` es el único texto",
                         "detente antes de redactar nada"):
            self.assertIn(fragment, policy)

    def test_agents_and_claude_v2_differ_only_in_the_opening(self):
        agents = AGENTS_V2_TEMPLATE.read_text(encoding="utf-8")
        claude = CLAUDE_V2_TEMPLATE.read_text(encoding="utf-8")
        for text in (agents, claude):
            self.assertEqual(text.count(COMMON_BEGIN), 1)
            self.assertEqual(common_block(text), "$common_policy")
            self.assertEqual(re.findall(r"^## .+$", text.split(COMMON_END)[1], re.M), [
                "## Arranque de cada conversación", "## Comandos reales del core",
                "## Preparación del personaje", "## Flujo narrativo de un turno",
                "## Canales que no se mezclan", "## Límites externos y preguntas sensibles"])
        self.assertEqual(agents.replace("Este `AGENTS.md` rige esta carpeta y todas sus "
                                        "subcarpetas para Codex. Un `AGENTS.md` más específico "
                                        "puede concretar trabajo futuro", "X"),
                         claude.replace("Este `CLAUDE.md` da a Claude las instrucciones de "
                                        "proyecto para esta carpeta y todas sus subcarpetas. "
                                        "Instrucciones más específicas pueden concretar trabajo "
                                        "futuro", "X"))

    def test_no_theme_urls_or_unknown_placeholders(self):
        for template in V2_TEMPLATES:
            text = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertIsNone(re.search(r"Nozomu|Naruto|Jcink|narutorol|https?://|"
                                            r"discord\.com", text))
                names = set(re.findall(r"\$(\w+)", text))
                self.assertLessEqual(names, {"display_name", "forum_id", "common_policy",
                                             "core_root_ps", "instance_root_ps"})
                self.assertNotIn("$$", text)

    def test_every_command_is_real_and_parses(self):
        parser = cli._build_parser()
        text = AGENTS_V2_TEMPLATE.read_text(encoding="utf-8")
        seen = set()
        for line in command_lines(text):
            concrete = line
            for placeholder, value in PLACEHOLDERS.items():
                concrete = concrete.replace(placeholder, value)
            argv = shlex.split(concrete)
            key = command_key(argv)
            seen.add(key)
            with self.subTest(line=line):
                self.assertIn(key, REAL_COMMANDS)
                self.assertNotIn("--json", argv)
                self.assertFalse({"--yes", "--force", "--nonce"} & set(argv))
                parser.parse_args(argv)  # a syntax error would raise SystemExit
        self.assertEqual(seen, REAL_COMMANDS)
        human = text.split("### Acciones humanas")[1].split("## Preparación")[0]
        self.assertEqual({command_key(shlex.split(line.replace("'", "")))
                          for line in command_lines(human)}, HUMAN_COMMANDS)
        agent = text.split("### Mutaciones que ejecutas tú")[1].split("### Acciones humanas")[0]
        self.assertEqual({command_key(shlex.split(line.replace("'", "")))
                          for line in command_lines(agent)},
                         {("character", "proposal", "add"), ("character", "draft", "create"),
                          ("narrative", "topic", "create"), ("narrative", "draft", "create")})
        self.assertFalse(re.search(r"\b(publish|send|export)\b", text))
        self.assertEqual(text.count("Push-Location '$core_root_ps'"), text.count("Pop-Location"))


class TemplateV2JsonShapesTest(unittest.TestCase):
    """The JSON shapes the v2 instructions show are the keys the real parsers accept."""

    def test_inline_json_keys(self):
        from core.runtime import character, narrative
        text = AGENTS_V2_TEMPLATE.read_text(encoding="utf-8")
        shapes = re.findall(r"`(\{.+?\})`", text)
        found = [set(re.findall(r'"(\w+)":', shape)) - {"candidate_id"} for shape in shapes]
        expected = [set(character._PROPOSAL_INPUT_KEYS), set(narrative._POST_INPUT_KEYS),
                    set(narrative._SEED_INPUT_KEYS), set(narrative._DRAFT_INPUT_KEYS),
                    set(narrative._PUBLICATION_INPUT_KEYS)]
        self.assertEqual(found, expected)
        for shape in shapes:
            if '"citations"' in shape:
                self.assertIn('{"candidate_id": "ID_OBJETO", "version": N}', shape)
        staff = text.split("`character staff record`. Su JSON tiene exactamente las claves ")[1]
        self.assertEqual(set(re.findall(r"`(\w+)`", staff.split("\n")[0])),
                         set(character._STAFF_INPUT_KEYS))


class RenderedV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        workspace = closed_workspace(cls.root)
        cls.output = cls.root / "instancia con 'comilla' y ñ"
        cls.instance = create_instance(workspace, output=cls.output, core_root=ROOT,
                                       instructions_version=2).instance

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def test_rendered_v2_files_are_exact(self):
        from tests import expected_instance_templates as expected
        root_ps = str(ROOT).replace("'", "''")
        instance_ps = str(self.output).replace("'", "''")
        for name, template in (("AGENTS.md", expected.EXPECTED_AGENTS_V2),
                               ("CLAUDE.md", expected.EXPECTED_CLAUDE_V2)):
            with self.subTest(name=name):
                wanted = (template.replace("$display_name", "Foro neutral de prueba")
                          .replace("$forum_id", "foro-neutral")
                          .replace("$common_policy", expected.EXPECTED_POLICY_V2)
                          .replace("$core_root_ps", root_ps)
                          .replace("$instance_root_ps", instance_ps))
                raw = (self.output / name).read_bytes()
                self.assertEqual(raw, wanted.encode("utf-8"))
                self.assertEqual(common_block(raw.decode("utf-8")), expected.EXPECTED_POLICY_V2)
                self.assertIn(f"--instance '{instance_ps}'", raw.decode("utf-8"))

    def test_render_function_with_the_v2_policy(self):
        config = self.instance.config
        self.assertEqual(render_instructions(AGENTS_V2_TEMPLATE, config,
                                             policy_template=POLICY_V2_TEMPLATE),
                         (self.output / "AGENTS.md").read_bytes())
        self.assertNotEqual(render_instructions(AGENTS_V2_TEMPLATE, config),
                            (self.output / "AGENTS.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
