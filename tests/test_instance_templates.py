import re
import shutil
import tempfile
import unittest
from pathlib import Path

from core.runtime.instance import (
    AGENTS_TEMPLATE,
    CLAUDE_TEMPLATE,
    COMMON_BEGIN,
    COMMON_END,
    INSTANCE_TEMPLATE,
    POLICY_TEMPLATE,
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


if __name__ == "__main__":
    unittest.main()
