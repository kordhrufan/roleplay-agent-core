import shutil
import tempfile
import unittest
from pathlib import Path

import adapters.manual as manual
from adapters.manual import ManualAdapterError, load_manual_dossier
from core.runtime.assimilation import DossierError, DossierSection, LoadedForumDossier

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"


class ManualAdapterTest(unittest.TestCase):
    def copy_fixture(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "expediente"
        shutil.copytree(FIXTURE, target)
        return target

    def replace(self, dossier_dir: Path, old: str, new: str) -> None:
        path = dossier_dir / "expediente.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_bytes(text.replace(old, new, 1).encode("utf-8"))

    def test_ready_fixture_loads(self):
        loaded = load_manual_dossier(FIXTURE)
        self.assertIsInstance(loaded, LoadedForumDossier)
        self.assertEqual(loaded.dossier.forum_id, "foro-neutral")

    def test_missing_required_section_blocks(self):
        dossier_dir = self.copy_fixture()
        self.replace(dossier_dir, "## Revisión del staff\n### Fuente\n",
                     "## Revisión del staff\nEstado: FALTA\n\n## Borrar\n### Fuente\n")
        text = (dossier_dir / "expediente.md").read_text(encoding="utf-8")
        start = text.index("\n## Borrar\n")
        end = text.index("\n## Plataforma y formato")
        (dossier_dir / "expediente.md").write_bytes((text[:start] + text[end:]).encode("utf-8"))
        with self.assertRaises(ManualAdapterError) as ctx:
            load_manual_dossier(dossier_dir)
        self.assertEqual(ctx.exception.assessment.missing_required, (DossierSection.STAFF_REVIEW,))
        self.assertIn("«Revisión del staff»", ctx.exception.reason)

    def test_missing_optional_section_is_allowed(self):
        dossier_dir = self.copy_fixture()
        self.replace(dossier_dir, "## Sistema de combate\nEstado: NO APLICA\n",
                     "## Sistema de combate\nEstado: FALTA\n")
        loaded = load_manual_dossier(dossier_dir)
        self.assertEqual(len(loaded.dossier.sections), 7)

    def test_dossier_errors_keep_their_cause(self):
        dossier_dir = self.copy_fixture()
        self.replace(dossier_dir, "forum_id: foro-neutral", "forum_id: Foro")
        with self.assertRaises(ManualAdapterError) as ctx:
            load_manual_dossier(dossier_dir)
        self.assertIsInstance(ctx.exception.__cause__, DossierError)
        self.assertEqual(ctx.exception.__cause__.line, 2)
        self.assertIsNone(ctx.exception.assessment)

    def test_has_no_reading_of_turns_or_publishing(self):
        names = {name.lower() for name in dir(manual)}
        for forbidden in ("forumreader", "publish", "post", "send", "turn"):
            self.assertFalse([n for n in names if forbidden in n], forbidden)


if __name__ == "__main__":
    unittest.main()
