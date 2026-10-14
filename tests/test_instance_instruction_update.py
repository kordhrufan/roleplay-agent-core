"""7b: `instance instructions update` replaces the v1 agent instructions by v2 and nothing else."""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from core.runtime import assimilation, cli, instance as instance_module, workspace as workspace_module
from core.runtime.instance import (
    AGENTS_V2_TEMPLATE,
    CLAUDE_V2_TEMPLATE,
    POLICY_V2_TEMPLATE,
    InstanceError,
    load_instance,
    render_instructions,
    update_instance_instructions,
    update_lock_path,
)
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run
from tests.test_narrative_workflow import NarrativeCase

CHANGED = {"AGENTS.md", "CLAUDE.md", "work/instructions.json", "work/integrity.json"}
REAL_REPLACE = os.replace
JSON_MESSAGE = ("la actualización humana de instrucciones no admite --json: ejecuta el comando en "
                "tu terminal y responde a la confirmación")


class MigrationCase(NarrativeCase):
    """A v1 instance with an approved character and a topic with every kind of event."""

    def setUp(self):
        super().setUp()
        self.new_topic()
        self.record_post()
        self.seed()
        self.ndraft()
        self.confirm(text="Texto final editado\n")
        self.before = self.tree()
        self.loaded_before = self.loaded()

    def tree(self):
        return {p.relative_to(self.instance).as_posix(): p.read_bytes()
                for p in sorted(self.instance.rglob("*")) if p.is_file()}

    def mtimes(self):
        return {p: p.stat().st_mtime_ns for p in self.instance.rglob("*") if p.is_file()}

    def migrate(self, terminal=None):
        return update_instance_instructions(self.instance, core_root=ROOT,
                                            terminal=terminal or FakeTerminal())

    def siblings(self):
        return sorted(p.name for p in self.root.iterdir() if p.name.startswith("."))

    def assert_untouched(self):
        self.assertEqual(self.tree(), self.before)
        self.assertEqual(self.loaded().instructions.version, 1)
        self.assertFalse(update_lock_path(self.instance).exists())

    def assert_conflict(self, action, *args, code="CONFLICT"):
        with self.assertRaises(InstanceError) as ctx:
            action(*args)
        self.assertEqual(ctx.exception.code, code, ctx.exception.reason)
        return ctx.exception


class MigrationTest(MigrationCase):
    def test_v1_to_v2_changes_only_the_instruction_set(self):
        terminal = FakeTerminal()
        result = self.migrate(terminal)
        after = self.tree()
        self.assertEqual({p for p in set(after) | set(self.before)
                          if after.get(p) != self.before.get(p)}, CHANGED)
        old = self.loaded_before.instructions
        new = result.instructions
        loaded = self.loaded()
        prompt, phrase = terminal.output.rsplit("Escribe exactamente: ", 1)
        self.assertEqual(prompt, (
            "ACTUALIZACIÓN HUMANA DE INSTRUCCIONES REQUERIDA\n"
            "Foro: foro-neutral\n"
            f"Instancia: {loaded.instance_root}\n"
            "Versión actual: 1\n"
            f"Conjunto actual SHA-256: {old.instructions_sha256}\n"
            f"AGENTS.md actual SHA-256: {old.files[0].sha256}\n"
            f"CLAUDE.md actual SHA-256: {old.files[1].sha256}\n"
            "Versión nueva: 2\n"
            f"Conjunto nuevo SHA-256: {new.instructions_sha256}\n"
            f"AGENTS.md nuevo SHA-256: {new.files[0].sha256}\n"
            f"CLAUDE.md nuevo SHA-256: {new.files[1].sha256}\n"
            f"Descriptor nuevo SHA-256: {new.descriptor_sha256}\n"
            "Se reemplazarán AGENTS.md y CLAUDE.md, se añadirá work/instructions.json y se "
            "regenerará work/integrity.json para cubrirlos.\n"
            "Se conservarán byte a byte instance.json, dossier/, corpus/, characters/ y "
            "narrative/.\n"
            "Esta acción cambia solo las instrucciones locales del agente; no cambia las normas del "
            "foro, no publica ni usa red.\n"))
        self.assertRegex(phrase, r"^ACTUALIZAR-INSTRUCCIONES foro-neutral v1-a-v2 "
                                 r"[A-HJ-NP-Z2-9]{8}\n> $")
        self.assertEqual((result.updated, result.previous, new.version, loaded.instructions),
                         (True, old, 2, new))
        config = loaded.config
        self.assertEqual(after["AGENTS.md"], render_instructions(
            AGENTS_V2_TEMPLATE, config, policy_template=POLICY_V2_TEMPLATE))
        self.assertEqual(after["CLAUDE.md"], render_instructions(
            CLAUDE_V2_TEMPLATE, config, policy_template=POLICY_V2_TEMPLATE))
        integrity = json.loads(after["work/integrity.json"])
        self.assertEqual(integrity["schema_version"], config.schema_version)
        self.assertIn("work/instructions.json", [f["path"] for f in integrity["files"]])
        self.assertEqual(instance_module._logical(loaded),
                         instance_module._logical(self.loaded_before))
        self.assertEqual(self.siblings(), [])
        # The agent keeps operating 7a on the migrated instance.
        self.assertEqual(self.record_post(post_id="respuesta-2", name="p2.json").post.position, 3)

    def test_retry_is_a_noop_without_prompt_lock_or_write(self):
        self.migrate()
        tree, mtimes = self.tree(), self.mtimes()
        terminal = FakeTerminal()
        with mock.patch.object(instance_module, "_corpus_lock") as lock:
            result = self.migrate(terminal)
        lock.assert_not_called()
        self.assertEqual((result.updated, terminal.output, result.previous, result.instructions),
                         (False, "", result.instructions, self.loaded().instructions))
        self.assertEqual((self.tree(), self.mtimes()), (tree, mtimes))
        self.assert_conflict(self.migrate, FakeTerminal(interactive=False), code="INVALID_STATE")

    def test_barrier_failures_write_nothing(self):
        for terminal in (FakeTerminal(interactive=False),
                         FakeTerminal(transform=lambda p: p.lower() + "\n"),
                         FakeTerminal(transform=lambda p: p.replace("v1-a-v2", "v1-a-v3") + "\n"),
                         FakeTerminal(transform=lambda p: None)):
            with self.subTest(terminal=terminal):
                self.assert_conflict(self.migrate, terminal, code="INVALID_STATE")
                self.assert_untouched()

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.migrate(FakeTerminal(on_read=interrupt))
        self.assert_untouched()
        self.assertEqual(self.siblings(), [])

    def test_the_corpus_update_phrase_does_not_authorize_it(self):
        terminal = FakeTerminal(transform=lambda p: p.replace("ACTUALIZAR-INSTRUCCIONES",
                                                              "ACTUALIZAR-INSTANCIA") + "\n")
        self.assert_conflict(self.migrate, terminal, code="INVALID_STATE")
        self.assert_untouched()


class ConcurrencyTest(MigrationCase):
    def test_changes_during_the_prompt_are_conflicts(self):
        counter = {"n": 0}

        def proposal():
            counter["n"] += 1
            self.add(proposal_id=f"carrera-{counter['n']}", text=f"# Aria\nCambio {counter['n']}\n")

        def post():
            counter["n"] += 1
            self.record_post(post_id=f"carrera-{counter['n']}", name="carrera.json")

        def topic_lock():
            self.topic_lock().write_bytes(b"")

        def leftover():
            (self.root / f".{self.instance.name}.update-backup-0011223344556677").mkdir()

        def other_migration():
            self.migrate()

        def corrupt_static():
            agents = self.instance / "AGENTS.md"
            agents.write_bytes(agents.read_bytes() + b" ")

        def corrupt_mutable():
            self.topic_path().write_bytes(self.topic_path().read_bytes() + b" ")

        for change in (proposal, post, topic_lock, leftover, corrupt_static, corrupt_mutable,
                       other_migration):
            with self.subTest(change=change.__name__):
                before = self.tree()
                self.assert_conflict(self.migrate, FakeTerminal(on_read=change))
                self.assertFalse(update_lock_path(self.instance).exists())
                if change is other_migration:
                    self.assertEqual(self.loaded().instructions.version, 2)
                    continue
                if change in (corrupt_static, corrupt_mutable):
                    # REV7B-02: a change that breaks loading is a conflict too; nothing written.
                    changed = self.tree()
                    self.assertFalse((self.instance / "work" / "instructions.json").exists())
                    self.assertEqual({p for p in set(changed) | set(before)
                                      if changed.get(p) != before.get(p)},
                                     {"AGENTS.md"} if change is corrupt_static
                                     else {"narrative/topics/escena/state.json"})
                    restored = self.instance / ("AGENTS.md" if change is corrupt_static
                                                else "narrative/topics/escena/state.json")
                    restored.write_bytes(before[restored.relative_to(self.instance).as_posix()])
                    self.assertEqual(self.tree(), before)
                    continue
                self.assertEqual(self.loaded().instructions.version, 1)
                if change is topic_lock:
                    self.topic_lock().unlink()
                    self.assertEqual(self.tree(), before)
                elif change is leftover:
                    shutil.rmtree(self.root / f".{self.instance.name}.update-backup-"
                                              "0011223344556677")
                    self.assertEqual(self.tree(), before)

    def test_locks_and_leftovers_stop_it_before_the_prompt(self):
        locks = (update_lock_path(self.instance), self.state_path().with_name("state.json.lock"),
                 self.instance / "characters" / ".nueva.create.lock", self.topic_lock(),
                 self.instance / "narrative" / "topics" / ".nuevo.create.lock",
                 self.root / f".{self.instance.name}.update-staging-0123456789abcdef")
        for lock in locks:
            with self.subTest(lock=lock.name):
                lock.write_bytes(b"")
                terminal = FakeTerminal()
                self.assert_conflict(self.migrate, terminal)
                self.assertEqual(terminal.output, "")
                lock.unlink()
                self.assert_untouched()
        self.assertTrue(self.migrate().updated)

    def test_narrative_writes_wait_while_the_instance_is_updating(self):
        update_lock_path(self.instance).write_bytes(b"")
        from core.memory.narrative import NarrativeError
        with self.assertRaises(NarrativeError) as ctx:
            self.record_post(post_id="bloqueado", name="b.json")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        update_lock_path(self.instance).unlink()


class FailureTest(MigrationCase):
    def flaky_replace(self, failing):
        def replace(src, dst, *args, **kwargs):
            if failing(Path(src), Path(dst)):
                raise PermissionError("simulado")
            return REAL_REPLACE(src, dst, *args, **kwargs)
        return replace

    def test_failures_before_publishing_leave_v1_intact(self):
        def failing_open(*args, **kwargs):
            raise OSError("disco lleno simulado")

        with mock.patch.object(instance_module, "open", failing_open, create=True):
            self.assert_conflict(self.migrate, code="IO")
        self.assert_untouched()
        replace = self.flaky_replace(lambda s, d: "update-backup" in d.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            self.assert_conflict(self.migrate, code="IO")
        self.assert_untouched()
        self.assertEqual(self.siblings(), [])

    def test_fsync_staging_load_and_staging_cleanup_failures(self):
        with mock.patch.object(instance_module.os, "fsync", side_effect=OSError("fsync")):
            self.assert_conflict(self.migrate, code="IO")
        self.assert_untouched()
        self.assertEqual(self.siblings(), [])
        real = instance_module._load_instance

        def failing_staging(physical, logical, core_root):
            if "update-staging" in Path(physical).name:
                raise InstanceError("INVALID_STATE", "staging simulado")
            return real(physical, logical, core_root)

        with mock.patch.object(instance_module, "_load_instance", failing_staging):
            self.assert_conflict(self.migrate, code="INVALID_STATE")
        self.assert_untouched()
        self.assertEqual(self.siblings(), [])
        real_rmtree = shutil.rmtree

        def stubborn(path, *args, **kwargs):
            if "update-staging" in Path(path).name:
                raise PermissionError("simulado")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(instance_module, "_load_instance", failing_staging), \
                mock.patch.object(workspace_module.shutil, "rmtree", stubborn):
            error = self.assert_conflict(self.migrate, code="INVALID_STATE")
        self.assertIn("bórrala a mano", error.reason)
        self.assert_untouched()
        staging = [p for p in self.root.iterdir() if "update-staging" in p.name]
        self.assertEqual(len(staging), 1)
        self.assert_conflict(self.migrate)  # the leftover stops the next attempt
        real_rmtree(staging[0])
        self.assertTrue(self.migrate().updated)

    def test_failed_publication_is_restored(self):
        replace = self.flaky_replace(lambda s, d: "update-staging" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            error = self.assert_conflict(self.migrate, code="IO")
        self.assertIn("se ha restaurado la anterior", error.reason)
        self.assert_untouched()
        self.assertEqual(self.siblings(), [])

    def test_failed_restore_keeps_two_complete_unmixed_trees(self):
        replace = self.flaky_replace(lambda s, d: "update-staging" in s.name
                                     or "update-backup" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            error = self.assert_conflict(self.migrate, code="IO")
        backup = next(p for p in self.root.iterdir() if "update-backup" in p.name)
        staging = next(p for p in self.root.iterdir() if "update-staging" in p.name)
        self.assertIn(str(backup), error.reason)
        self.assertFalse(self.instance.exists())
        self.assertFalse((backup / "work" / "instructions.json").exists())
        self.assertTrue((staging / "work" / "instructions.json").exists())
        staged_agents = (staging / "AGENTS.md").read_bytes()
        self.assertIn("Comandos reales del core".encode(), staged_agents)
        self.assertIn("Comandos reales del core".encode(), (staging / "CLAUDE.md").read_bytes())
        # Any later update refuses to ignore the leftovers.
        backup.rename(self.instance)
        self.assert_untouched()
        self.assert_conflict(self.migrate)
        shutil.rmtree(staging)
        self.assertTrue(self.migrate().updated)

    def test_failed_verification_after_publishing_keeps_the_backup(self):
        real = instance_module._load_instance
        staged = []

        def checking(physical, logical, core_root):
            if "update-staging" in Path(physical).name:
                staged.append(True)
            elif staged and Path(physical) == self.instance:
                raise InstanceError("INVALID_STATE", "simulado")
            return real(physical, logical, core_root)

        with mock.patch.object(instance_module, "_load_instance", checking):
            error = self.assert_conflict(self.migrate, code="IO")
        backup = next(p for p in self.root.iterdir() if "update-backup" in p.name)
        self.assertIn(str(backup), error.reason)
        shutil.rmtree(self.instance)
        backup.rename(self.instance)
        self.assert_untouched()

    def test_backup_removal_failure_is_reported_after_applying(self):
        real_rmtree = shutil.rmtree

        def rmtree(path, *args, **kwargs):
            if "update-backup" in Path(path).name:
                raise PermissionError("simulado")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(workspace_module.shutil, "rmtree", rmtree):
            error = self.assert_conflict(self.migrate, code="IO")
        self.assertIn("se actualizó", error.reason)
        self.assertEqual(self.loaded().instructions.version, 2)
        for leftover in self.root.iterdir():
            if "update-backup" in leftover.name:
                real_rmtree(leftover)

    def test_lock_release_failure_is_reported(self):
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".instance-update.lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            error = self.assert_conflict(self.migrate, code="IO")
        self.assertIn("el cambio se guardó", error.reason)
        update_lock_path(self.instance).unlink()
        self.assertEqual(self.loaded().instructions.version, 2)


class ModelTest(MigrationCase):
    def test_instructions_are_mandatory_in_a_loaded_instance(self):
        import dataclasses
        from core.runtime.instance import LoadedInstance
        field = next(f for f in dataclasses.fields(LoadedInstance) if f.name == "instructions")
        self.assertIs(field.default, dataclasses.MISSING)
        loaded = self.loaded()
        with self.assertRaises(InstanceError):
            dataclasses.replace(loaded, instructions=None)
        self.migrate()
        self.assertEqual(self.loaded().instructions.version, 2)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_work_folder_or_descriptor_through_a_link_is_rejected(self):
        import _winapi
        self.migrate()
        work = self.instance / "work"
        aside = self.root / "work-real"
        work.rename(aside)
        try:
            _winapi.CreateJunction(str(aside), str(work))
        except OSError as exc:
            aside.rename(work)
            self.skipTest(f"no se pudo crear una junction: {exc}")
        with self.assertRaises(InstanceError):
            self.loaded()
        os.rmdir(work)
        aside.rename(work)
        descriptor = work / "instructions.json"
        data = descriptor.read_bytes()
        target = self.root / "descriptor-real.json"
        target.write_bytes(data)
        descriptor.unlink()
        try:
            os.symlink(target, descriptor)
        except OSError:
            descriptor.write_bytes(data)
            self.skipTest("este Windows no permite crear enlaces simbólicos a archivos")
        with self.assertRaises(InstanceError):
            self.loaded()
        descriptor.unlink()
        descriptor.write_bytes(data)
        self.assertEqual(self.loaded().instructions.version, 2)


class CliTest(MigrationCase):
    def argv(self):
        return ["instance", "instructions", "update", "--instance", str(self.instance)]

    def test_outputs_json_rejection_and_tty(self):
        code, out, _ = run("--json", *self.argv())
        self.assertEqual((code, json.loads(out)), (3, {"ok": False, "code": "INVALID_STATE",
                                                       "message": JSON_MESSAGE}))
        code, out, err = run(*self.argv(), stdin="ACTUALIZAR-INSTRUCCIONES foro-neutral v1-a-v2 "
                                                 "ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("terminal interactiva", err)
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *self.argv()],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(b"ACTUALIZAR-INSTRUCCIONES", result.stdout)
        self.assert_untouched()
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            code, out, _ = run(*self.argv())
        new = self.loaded().instructions
        self.assertEqual((code, out), (0, "Instrucciones actualizadas: foro-neutral | v1 -> v2 | "
                                          f"conjunto sha256={new.instructions_sha256}.\n"))
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            code, out, _ = run(*self.argv())
        self.assertEqual((code, out), (0, "Instrucciones ya actualizadas: foro-neutral | v2 | "
                                          f"conjunto sha256={new.instructions_sha256}.\n"))
        update_lock_path(self.instance).write_bytes(b"")
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            self.assertEqual(run(*self.argv())[0], 0)  # the no-op needs no lock
        update_lock_path(self.instance).unlink()

    def test_parser(self):
        for argv in (["instance", "instructions", "update"],
                     ["instance", "instructions", "update", "--instance", "x", "--yes"],
                     ["instance", "instructions", "update", "--instance", "x", "--version", "2"],
                     ["instance", "instructions", "downgrade", "--instance", "x"],
                     ["instance", "instructions"],
                     ["instance", "init", "--workspace", "x", "--output", "y",
                      "--instructions-version", "3"],
                     ["instance", "init", "--workspace", "x", "--output", "y",
                      "--instructions-version", "dos"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)
        self.assertTrue(re.search(r"--instructions-version \{1,2\}",
                                  run("instance", "init", "--help")[1]))


if __name__ == "__main__":
    unittest.main()
