import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.runtime import cli
from core.runtime.workspace import WorkspaceError
from core.runtime.workspace import create_workspace
from adapters.manual import load_manual_dossier

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dossier = self.root / "expediente"
        shutil.copytree(FIXTURE, self.dossier)
        self.workspace = self.root / "ws"

    def assert_error(self, out: str, code: str) -> None:
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "code", "message"})
        self.assertEqual((payload["ok"], payload["code"]), (False, code))
        self.assertTrue(payload["message"])

    def init(self, *extra: str, workspace: Path | str | None = None) -> tuple[int, str, str]:
        target = str(workspace if workspace is not None else self.workspace)
        return run(*extra, "assimilation", "init", "--dossier", str(self.dossier),
                   "--workspace", target)


class ParserTest(CliTestCase):
    def test_import_has_no_side_effects(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            importlib.reload(cli)
        self.assertEqual(out.getvalue(), "")

    def test_required_flags(self):
        for argv in (["assimilation", "init", "--dossier", str(self.dossier)],
                     ["assimilation", "init", "--workspace", str(self.workspace)],
                     ["assimilation", "status"], ["assimilation"], []):
            with self.subTest(argv=argv):
                code, _, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("usage", err)
        self.assertFalse(self.workspace.exists())

    def test_no_publication_or_instance_commands(self):
        for command in ("instance", "publish", "send", "post"):
            with self.subTest(command=command):
                self.assertEqual(run(command)[0], 2)
        help_text = cli._build_parser().format_help().lower()
        for word in ("publish", "publica ", "send", "post"):
            self.assertNotIn(word, help_text.replace("no publica nada", ""))


class InitTest(CliTestCase):
    def test_json_success_and_retry(self):
        code, out, _ = self.init("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "action": "assimilation.init", "created": True,
                                           "forum_id": "foro-neutral", "workspace": str(self.workspace)})
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.workspace.rglob("*") if p.is_file()}
        code, out, _ = self.init("--json")
        self.assertEqual((code, json.loads(out)["created"]), (0, False))
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.workspace.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_text_output(self):
        code, out, _ = self.init()
        self.assertEqual(code, 0)
        self.assertIn("Workspace creado", out)
        self.assertIn("foro-neutral", out)
        code, out, _ = self.init()
        self.assertIn("ya existía", out)

    def test_relative_workspace_is_resolved_from_cwd(self):
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        code, out, _ = self.init("--json", workspace="relativo")
        self.assertEqual(code, 0)
        self.assertEqual(Path(json.loads(out)["workspace"]), self.root / "relativo")
        self.assertTrue((self.root / "relativo" / "workspace.json").is_file())

    def test_unsafe_destinations(self):
        (self.root / "ocupado").mkdir()
        (self.root / "ocupado" / "algo.txt").write_bytes(b"x")
        (self.root / "archivo").write_bytes(b"x")
        cases = {
            "inside checkout": ROOT / "tests" / "no-crear-aqui",
            "checkout itself": ROOT,
            "inside dossier": self.dossier / "ws",
            "dossier itself": self.dossier,
            "ancestor of dossier": self.root,
            "missing parent": self.root / "no-existe" / "ws",
            "non-empty": self.root / "ocupado",
            "file": self.root / "archivo",
        }
        for name, target in cases.items():
            with self.subTest(name):
                code, out, _ = self.init("--json", workspace=target)
                self.assertEqual(code, 4, out)
                self.assert_error(out, "UNSAFE_DESTINATION" if name != "non-empty" else "CONFLICT")
        self.assertFalse((ROOT / "tests" / "no-crear-aqui").exists())
        self.assertFalse((self.dossier / "ws").exists())
        self.assertFalse((self.root / "no-existe").exists())
        self.assertEqual([p.name for p in (self.root / "ocupado").iterdir()], ["algo.txt"])

    def test_symlinked_destination(self):
        real = self.root / "real"
        real.mkdir()
        try:
            os.symlink(real, self.root / "enlace", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("el sistema no permite crear enlaces simbólicos a este usuario")
        code, _, _ = self.init(workspace=self.root / "enlace")
        self.assertEqual(code, 4)
        self.assertEqual(list(real.iterdir()), [])

    def test_dossier_not_ready_or_invalid(self):
        path = self.dossier / "expediente.md"
        path.write_bytes(path.read_bytes().replace(b"forum_id: foro-neutral", b"forum_id: X"))
        code, _, err = self.init()
        self.assertEqual(code, 3)
        self.assertIn("forum_id", err)
        self.assertFalse(self.workspace.exists())
        code, _, _ = run("assimilation", "init", "--dossier", str(ROOT / "core" / "runtime" / "templates"),
                         "--workspace", str(self.workspace))
        self.assertEqual(code, 3)

    def test_changed_dossier_conflicts_with_existing_workspace(self):
        self.assertEqual(self.init()[0], 0)
        manual = self.dossier / "materials" / "manual-foro.md"
        manual.write_bytes(manual.read_bytes() + b"Cambio.\n")
        code, out, _ = self.init("--json")
        self.assertEqual(code, 4)
        self.assert_error(out, "CONFLICT")


class StatusTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.init()[0], 0)

    def status(self, *extra: str) -> tuple[int, str, str]:
        return run(*extra, "assimilation", "status", "--workspace", str(self.workspace))

    def test_ok(self):
        code, out, _ = self.status("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "action": "assimilation.status",
                                           "forum_id": "foro-neutral", "integrity": "OK",
                                           "workspace": str(self.workspace)})
        code, out, _ = self.status()
        self.assertIn("íntegro", out)

    def test_detects_manual_edits(self):
        for relative in ("workspace.json", "work/integrity.json", "corpus/state.json",
                         "dossier/expediente.md", "dossier/materials/material-suelto.md"):
            with self.subTest(relative=relative):
                path = self.workspace / relative
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                code, out, _ = self.status("--json")
                self.assertEqual(code, 3)
                self.assert_error(out, "INVALID_STATE")
                path.write_bytes(original)
                self.assertEqual(self.status()[0], 0)

    def test_other_checkout_conflicts(self):
        fake = self.root / "otro-checkout"
        (fake / "core" / "runtime").mkdir(parents=True)
        (fake / "core" / "runtime" / "cli.py").write_bytes(b"")
        other = self.root / "ws-otro"
        create_workspace(load_manual_dossier(self.dossier), dossier_dir=self.dossier,
                         workspace=other, core_root=fake)
        code, out, _ = run("--json", "assimilation", "status", "--workspace", str(other))
        self.assertEqual(code, 4)
        self.assert_error(out, "CONFLICT")

    def test_missing_workspace(self):
        code, _, _ = run("assimilation", "status", "--workspace", str(self.root / "no-existe"))
        self.assertEqual(code, 3)


class ErrorShapeTest(CliTestCase):
    def test_codes_3_4_5_use_the_contracted_json(self):
        code, out, _ = run("--json", "assimilation", "status", "--workspace", str(self.root / "no"))
        self.assertEqual(code, 3)
        self.assert_error(out, "INVALID_STATE")
        code, out, _ = self.init("--json", workspace=ROOT / "tests" / "no-crear-aqui")
        self.assertEqual(code, 4)
        self.assert_error(out, "UNSAFE_DESTINATION")
        with mock.patch.object(cli, "load_workspace", side_effect=WorkspaceError("IO", "disco")):
            code, out, _ = run("--json", "assimilation", "status", "--workspace", str(self.root))
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out), {"ok": False, "code": "IO", "message": "disco"})


@unittest.skipUnless(os.name == "nt", "rutas de dispositivo y junctions son de Windows")
class WindowsPathTest(CliTestCase):
    def junction(self, target: Path, link: Path) -> None:
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, AttributeError, OSError) as exc:
            self.skipTest(f"no se pudo crear una junction: {exc}")

    def test_device_prefix_cannot_reach_the_checkout(self):
        target = "\\\\?\\" + str(ROOT / "tests" / "no-crear-aqui")
        self.assertTrue(target.startswith(chr(92) * 2 + "?" + chr(92)))
        code, out, _ = self.init("--json", workspace=target)
        self.assertEqual(code, 4)
        self.assert_error(out, "UNSAFE_DESTINATION")
        self.assertFalse((ROOT / "tests" / "no-crear-aqui").exists())

    def test_case_variant_cannot_reach_the_checkout(self):
        target = str(ROOT / "tests" / "no-crear-aqui").upper()
        self.assertEqual(self.init(workspace=target)[0], 4)
        self.assertFalse((ROOT / "tests" / "no-crear-aqui").exists())

    def test_junction_destination_is_rejected(self):
        real = self.root / "real"
        real.mkdir()
        self.junction(real, self.root / "enlace")
        code, out, _ = self.init("--json", workspace=self.root / "enlace")
        self.assertEqual(code, 4)
        self.assert_error(out, "UNSAFE_DESTINATION")
        self.assertTrue((self.root / "enlace").exists())
        self.assertEqual(list(real.iterdir()), [])

    def test_junction_inside_workspace_is_rejected(self):
        self.assertEqual(self.init()[0], 0)
        outside = self.root / "fuera"
        shutil.copytree(self.workspace / "dossier", outside)
        shutil.rmtree(self.workspace / "dossier")
        self.junction(outside, self.workspace / "dossier")
        code, out, _ = run("--json", "assimilation", "status", "--workspace", str(self.workspace))
        self.assertEqual(code, 3)
        self.assert_error(out, "INVALID_STATE")

    def test_junction_to_checkout_cannot_be_used_as_destination(self):
        self.junction(ROOT / "tests", self.root / "al-repo")
        code, _, _ = self.init(workspace=self.root / "al-repo" / "no-crear-aqui")
        self.assertEqual(code, 4)
        self.assertFalse((ROOT / "tests" / "no-crear-aqui").exists())


class SubprocessTest(CliTestCase):
    def test_happy_path_as_module(self):
        command = [sys.executable, "-B", "-m", "core.runtime.cli", "--json", "assimilation"]
        init = subprocess.run(command + ["init", "--dossier", str(self.dossier), "--workspace",
                                         str(self.workspace)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertTrue(json.loads(init.stdout)["created"])
        status = subprocess.run(command + ["status", "--workspace", str(self.workspace)],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["integrity"], "OK")


if __name__ == "__main__":
    unittest.main()
