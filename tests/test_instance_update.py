import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from core.runtime import assimilation, instance as instance_module, workspace as workspace_module
from core.runtime.assimilation import LEGACY_FORMAT, ADDITIVE_FORMAT
from core.runtime.character import (
    add_proposal,
    create_draft,
    get_effective_composition,
    import_concept,
    record_proposal_decision,
    record_staff_response,
)
from core.character.models import CharacterError
from core.review.models import ReviewStatus
from core.runtime.instance import (
    AGENTS_TEMPLATE,
    CLAUDE_TEMPLATE,
    InstanceError,
    approved_corpus,
    closed_corpus_of,
    load_instance,
    render_instructions,
    snapshot_for_candidate,
    update_instance,
    update_instance_instructions,
    update_lock_path,
)
from core.runtime import cli
from core.memory.narrative import NarrativeError, context_sha256
from core.runtime.narrative import (
    confirm_narrative_publication,
    create_narrative_draft,
    create_topic,
    import_human_seed,
    record_external_post,
)
from core.runtime.persistence import load_state
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run
from tests.test_corpus_expansion import ExpansionCase, new_candidate, successor_dossier

REAL_REPLACE = os.replace


class UpdateCase(ExpansionCase):
    def setUp(self):
        super().setUp()
        concept = self.root / "concepto.md"
        concept.write_bytes("# Aria\nExploradora.\n".encode("utf-8"))
        import_concept(self.instance, expected_core_root=ROOT, character_id="aria", version=1,
                       input_path=concept, terminal=FakeTerminal())
        effective = get_effective_composition(self.loaded_instance(), character_id="aria")
        add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
            "proposal_id": "pendiente", "version": 1,
            "base_composition_sha256": effective.composition_sha256, "text": "Otra\n",
            "rationale": "Motivo", "citations": [{"candidate_id": "normas", "version": 3}]})
        add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
            "proposal_id": "rechazada", "version": 1,
            "base_composition_sha256": effective.composition_sha256, "text": "No\n",
            "rationale": "Motivo", "citations": [{"candidate_id": "normas", "version": 3}]})
        record_proposal_decision(self.instance, expected_core_root=ROOT, character_id="aria",
                                 proposal_id="rechazada", version=1,
                                 review_status=ReviewStatus.REJECTED, terminal=FakeTerminal())
        add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
            "proposal_id": "aceptada", "version": 1,
            "base_composition_sha256": effective.composition_sha256, "text": "Sí\n",
            "rationale": "Motivo", "citations": [{"candidate_id": "mundo", "version": 1}]})
        record_proposal_decision(self.instance, expected_core_root=ROOT, character_id="aria",
                                 proposal_id="aceptada", version=1,
                                 review_status=ReviewStatus.APPROVED, terminal=FakeTerminal())
        effective = get_effective_composition(self.loaded_instance(), character_id="aria")
        sheet = self.root / "ficha.md"
        sheet.write_bytes(b"# Ficha\n")
        draft = create_draft(self.instance, expected_core_root=ROOT, character_id="aria",
                             version=1, composition_sha256=effective.composition_sha256,
                             input_path=sheet)
        response = self.root / "respuesta.json"
        response.write_bytes(json.dumps({
            "draft_sha256": draft.draft.record.draft_sha256, "locator": "https://foro.example/1",
            "observed_at": "2026-10-14T10:00:00+02:00", "response": "Aprobada."}).encode())
        record_staff_response(self.instance, expected_core_root=ROOT, character_id="aria",
                              version=1, review_status=ReviewStatus.APPROVED,
                              input_path=response, terminal=FakeTerminal())

    def loaded_instance(self):
        return load_instance(self.instance, expected_core_root=ROOT)

    def characters(self):
        folder = self.instance / "characters"
        return {p.relative_to(folder).as_posix(): p.read_bytes()
                for p in sorted(folder.rglob("*")) if p.is_file()}

    def statics(self):
        return {p.relative_to(self.instance).as_posix(): p.read_bytes()
                for p in sorted(self.instance.rglob("*"))
                if p.is_file() and not p.relative_to(self.instance).as_posix().startswith(
                    "characters/")}

    def update(self, terminal=None, workspace=None):
        return update_instance(self.instance, workspace_root=workspace or self.workspace,
                               core_root=ROOT, terminal=terminal or FakeTerminal())

    def siblings(self):
        return sorted(p.name for p in self.root.iterdir() if p.name.startswith("."))


class UpdateTest(UpdateCase):
    def test_v1_to_v2_preserves_characters_and_extends_the_corpus(self):
        self.closed_round()
        before = self.loaded_instance()
        characters = self.characters()
        agents, claude = ((self.instance / name).read_bytes() for name in ("AGENTS.md",
                                                                           "CLAUDE.md"))
        loaded = self.loaded()
        terminal = FakeTerminal()
        result = self.update(terminal)
        prompt, phrase = terminal.output.rsplit("Escribe exactamente: ", 1)
        self.assertEqual(prompt, (
            "ACTUALIZACIÓN HUMANA DE INSTANCIA REQUERIDA\n"
            "Foro: foro-neutral\n"
            f"Instancia: {before.instance_root}\n"
            "Expediente: 2026-10-11 -> 2026-10-14\n"
            f"Snapshot actual SHA-256: {before.closure.snapshot_sha256}\n"
            f"Snapshot nuevo SHA-256: {loaded.closure.snapshot_sha256}\n"
            "Nuevos aprobados: 1; nuevos rechazados: 0\n"
            "Personajes preservados: 1\n"
            "Esta acción reemplaza solo los archivos estáticos; no cambia revisiones ni "
            "contenido de characters/.\n"))
        self.assertRegex(phrase, r"^ACTUALIZAR-INSTANCIA foro-neutral r2 [A-HJ-NP-Z2-9]{8}\n> $")
        self.assertTrue(result.updated)
        self.assertEqual(result.previous_snapshot_sha256, before.closure.snapshot_sha256)
        after = self.loaded_instance()
        self.assertEqual(after.config.schema_version, 2)
        self.assertEqual(after.config.dossier_version, "2026-10-14")
        self.assertEqual(self.characters(), characters)
        self.assertEqual([(c.state_revision, c.state) for c in after.characters],
                         [(c.state_revision, c.state) for c in before.characters])
        self.assertEqual(((self.instance / "AGENTS.md").read_bytes(),
                          (self.instance / "CLAUDE.md").read_bytes()), (agents, claude))
        self.assertEqual(render_instructions(AGENTS_TEMPLATE, after.config), agents)
        self.assertEqual(render_instructions(CLAUDE_TEMPLATE, after.config), claude)
        integrity = json.loads((self.instance / "work" / "integrity.json").read_text("utf-8"))
        self.assertEqual(integrity["schema_version"], 2)
        old = {e.candidate.key for e in approved_corpus(before)}
        new = {e.candidate.key for e in approved_corpus(after)}
        self.assertEqual(new - old, {("hielo", 1)})
        chain = closed_corpus_of(after)
        self.assertEqual([s.format for s in chain.snapshots], [LEGACY_FORMAT, ADDITIVE_FORMAT])
        self.assertEqual(chain.snapshot_for("normas", 3).ordinal, 1)
        self.assertEqual(chain.snapshot_for("hielo", 1).ordinal, 2)
        self.assertEqual(self.siblings(), [])
        # The old citations still resolve and new ones can be used.
        effective = get_effective_composition(after, character_id="aria")
        added = add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
            "proposal_id": "nueva", "version": 1,
            "base_composition_sha256": effective.composition_sha256, "text": "Con hielo\n",
            "rationale": "Usa la fuente nueva",
            "citations": [{"candidate_id": "hielo", "version": 1}]})
        self.assertTrue(added.created)

    def test_retry_is_a_noop_without_prompt(self):
        self.closed_round()
        self.update()
        statics, characters = self.statics(), self.characters()
        mtime = os.stat(self.instance / "instance.json").st_mtime_ns
        terminal = FakeTerminal()
        result = self.update(terminal)
        self.assertEqual((result.updated, terminal.output), (False, ""))
        self.assertEqual((self.statics(), self.characters()), (statics, characters))
        self.assertEqual(os.stat(self.instance / "instance.json").st_mtime_ns, mtime)
        with self.assertRaises(InstanceError):
            self.update(FakeTerminal(interactive=False))

    def test_refusals(self):
        self.extend()
        with self.assertRaises(InstanceError) as ctx:
            self.update()
        self.assertEqual(ctx.exception.code, "INVALID_STATE")  # round still open
        self.add(new_candidate())
        self.decide()
        self.close()
        other = self.root / "otra"
        other_dossier = successor_dossier(self.root, "exp-b", version="2026-10-16")
        self.extend(dossier_dir=other_dossier, workspace=other)
        self.add_to(other, new_candidate("rama"))
        self.update()
        with self.assertRaises(InstanceError) as ctx:
            self.update(workspace=other)
        self.assertEqual(ctx.exception.code, "INVALID_STATE")  # still open: not closed
        statics = self.statics()
        terminal = FakeTerminal()
        with self.assertRaises(InstanceError):
            self.update(FakeTerminal(interactive=False), workspace=other)
        self.assertEqual((self.statics(), terminal.output), (statics, ""))

    def add_to(self, workspace, value):
        from core.runtime.assimilation import add_candidate
        from core.runtime.workspace import CORPUS_STATE, load_workspace
        loaded = load_workspace(workspace)
        add_candidate(workspace / CORPUS_STATE, dossier=loaded.dossier,
                      expected_revision=loaded.corpus_revision, value=value,
                      context=loaded.expansion)

    def test_a_forked_or_stale_base_is_a_conflict(self):
        self.closed_round()
        fork = self.root / "bifurcada"
        fork_dossier = successor_dossier(self.root, "exp-f", version="2026-10-17")
        self.extend(dossier_dir=fork_dossier, workspace=fork)
        self.add_to(fork, new_candidate("rama"))
        from core.runtime.assimilation import close_expansion, record_candidate_decision
        from core.runtime.workspace import CORPUS_STATE, load_workspace
        loaded = load_workspace(fork)
        record_candidate_decision(fork / CORPUS_STATE, dossier=loaded.dossier,
                                  expected_revision=loaded.corpus_revision, candidate_id="rama",
                                  version=1, review_status=ReviewStatus.APPROVED,
                                  terminal=FakeTerminal(), context=loaded.expansion)
        loaded = load_workspace(fork)
        close_expansion(fork / CORPUS_STATE, dossier=loaded.dossier, context=loaded.expansion,
                        expected_revision=loaded.corpus_revision, terminal=FakeTerminal())
        self.update()
        statics = self.statics()
        terminal = FakeTerminal()
        with self.assertRaises(InstanceError) as ctx:
            self.update(terminal, workspace=fork)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        self.assertEqual(self.statics(), statics)
        with self.assertRaises(InstanceError) as ctx:
            from core.runtime.instance import create_instance
            create_instance(fork, output=self.root / "nueva", core_root=ROOT)


class ChainTest(UpdateCase):
    def test_v2_to_v2_keeps_every_character_byte_and_origin(self):
        characters = self.characters()
        states = [(c.state_revision, c.state) for c in self.loaded_instance().characters]
        self.closed_round()
        self.update()
        third = successor_dossier(self.root, "exp3", version="2026-10-20", edit=lambda t, d: t.replace(
            "Las del sur, del fuego.\n~~~~\n",
            'Las del sur, del fuego.\n~~~~\n\n### Fuente\nMetadatos: id="mares" | versión="1" | '
            'autoridad="Staff" | alcance="foro"\n~~~~ texto\nEl mar no tiene fondo.\n~~~~\n'))
        self.workspace = self.root / "ampliacion-3"
        value = new_candidate("mar", quote="El mar no tiene fondo.")
        value["citations"][0]["source_id"] = "mares"
        create_expansion = self.extend(dossier_dir=third)
        self.assertEqual(create_expansion.workspace.expansion.base.current.format, ADDITIVE_FORMAT)
        self.add(value)
        self.decide("mar")
        self.close()
        terminal = FakeTerminal()
        self.assertTrue(self.update(terminal).updated)
        self.assertIn("ACTUALIZAR-INSTANCIA foro-neutral r3", terminal.output)
        after = self.loaded_instance()
        self.assertEqual(self.characters(), characters)
        self.assertEqual([(c.state_revision, c.state) for c in after.characters], states)
        self.assertEqual([s.format for s in closed_corpus_of(after).snapshots],
                         [LEGACY_FORMAT, ADDITIVE_FORMAT, ADDITIVE_FORMAT])
        self.assertEqual([snapshot_for_candidate(after, candidate_id=c, version=1).ordinal
                          for c in ("mundo", "hielo", "mar")], [1, 2, 3])
        with self.assertRaises(InstanceError):
            snapshot_for_candidate(after, candidate_id="nada", version=1)
        self.assertEqual(self.siblings(), [])

    def test_snapshot_for_candidate_on_a_v1_instance(self):
        legacy = closed_corpus_of(self.loaded_instance()).current
        self.assertEqual(snapshot_for_candidate(self.loaded_instance(), candidate_id="normas",
                                                version=3), legacy)
        with self.assertRaises(InstanceError):
            snapshot_for_candidate(self.loaded_instance(), candidate_id="hielo", version=1)


class StableReadTest(UpdateCase):
    """REV5A-03: what is confirmed is what is applied; REV5A-04: leftovers stop the update."""

    def other_closed_round(self, name="otra", version="2026-10-18"):
        saved = self.workspace
        self.workspace = self.root / name
        self.extend(dossier_dir=successor_dossier(self.root, f"exp-{name}", version=version))
        self.add(new_candidate())
        self.decide()
        self.close()
        other, self.workspace = self.workspace, saved
        return other

    def test_workspace_swapped_while_planning_is_a_conflict(self):
        self.closed_round()
        other = self.other_closed_round()
        statics = self.statics()
        real_load = instance_module.load_workspace
        swapped = []

        def swapping(root, **kwargs):
            if not swapped:
                swapped.append(True)
                shutil.rmtree(self.workspace)
                shutil.copytree(other, self.workspace)
            return real_load(root, **kwargs)

        terminal = FakeTerminal()
        with mock.patch.object(instance_module, "load_workspace", swapping):
            with self.assertRaises(InstanceError) as ctx:
                self.update(terminal)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        self.assertEqual(self.statics(), statics)

    def test_workspace_swapped_during_the_prompt_is_a_conflict(self):
        self.closed_round()
        other = self.other_closed_round()
        statics = self.statics()

        def swap():
            shutil.rmtree(self.workspace)
            shutil.copytree(other, self.workspace)

        with self.assertRaises(InstanceError) as ctx:
            self.update(FakeTerminal(on_read=swap))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.statics(), statics)
        self.assertEqual(self.loaded_instance().config.schema_version, 1)

    def test_character_created_while_planning_is_a_conflict(self):
        self.closed_round()
        statics, characters = self.statics(), self.characters()
        real_load = instance_module.load_instance
        created = []

        def creating(root, **kwargs):
            result = real_load(root, **kwargs)
            if not created:
                created.append(True)
                import_concept(self.instance, expected_core_root=ROOT, character_id="beta",
                               version=1, input_path=self.root / "concepto.md",
                               terminal=FakeTerminal())
            return result

        terminal = FakeTerminal()
        with mock.patch.object(instance_module, "load_instance", creating):
            with self.assertRaises(InstanceError) as ctx:
                self.update(terminal)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        self.assertEqual(self.statics(), statics)
        terminal = FakeTerminal()
        self.update(terminal)
        self.assertIn("Personajes preservados: 2", terminal.output)
        self.assertEqual(len(self.loaded_instance().characters), 2)

    def test_leftovers_of_an_earlier_update_stop_it(self):
        self.closed_round()
        statics = self.statics()
        for leftover, make in (
            (f".{self.instance.name}.update-backup-deadbeefdeadbeef", lambda p: p.mkdir()),
            (f".{self.instance.name}.update-staging-0123456789abcdef",
             lambda p: p.write_bytes(b"x")),
        ):
            with self.subTest(leftover):
                path = self.root / leftover
                make(path)
                terminal = FakeTerminal()
                with self.assertRaises(InstanceError) as ctx:
                    self.update(terminal)
                self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
                self.assertIn(str(path), ctx.exception.reason)
                self.assertEqual(self.statics(), statics)
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        self.assertTrue(self.update().updated)
        (self.root / f".{self.instance.name}.update-backup-cafecafecafecafe").mkdir()
        with self.assertRaises(InstanceError):
            self.update()  # even the no-op refuses to ignore a leftover


class ConcurrencyTest(UpdateCase):
    def test_changes_during_the_prompt_are_conflicts(self):
        self.closed_round()
        statics = self.statics()

        def character_change():
            effective = get_effective_composition(self.loaded_instance(), character_id="aria")
            add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
                "proposal_id": "carrera", "version": 1,
                "base_composition_sha256": effective.composition_sha256, "text": "C\n",
                "rationale": "R", "citations": [{"candidate_id": "normas", "version": 3}]})

        with self.assertRaises(InstanceError) as ctx:
            self.update(FakeTerminal(on_read=character_change))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.statics(), statics)
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        self.assertFalse(update_lock_path(self.instance).exists())
        self.assertEqual(self.siblings(), [])

    def test_locks_block_both_sides(self):
        self.closed_round()
        character_lock = self.instance / "characters" / "aria" / "state.json.lock"
        create_lock = self.instance / "characters" / ".nueva.create.lock"
        for lock in (character_lock, create_lock):
            with self.subTest(lock=lock.name):
                lock.write_bytes(b"")
                terminal = FakeTerminal()
                with self.assertRaises(InstanceError) as ctx:
                    self.update(terminal)
                self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
                if lock is create_lock:
                    self.assertEqual(len(self.loaded_instance().characters), 1)  # ignored
                lock.unlink()
        update_lock = update_lock_path(self.instance)
        update_lock.write_bytes(b"")
        terminal = FakeTerminal()
        with self.assertRaises(InstanceError) as ctx:
            self.update(terminal)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        effective = get_effective_composition(self.loaded_instance(), character_id="aria")
        before = self.characters()
        operations = {
            "proposal": lambda t: add_proposal(
                self.instance, expected_core_root=ROOT, character_id="aria", value={
                    "proposal_id": "bloqueada", "version": 1,
                    "base_composition_sha256": effective.composition_sha256, "text": "B\n",
                    "rationale": "R", "citations": [{"candidate_id": "normas", "version": 3}]}),
            "decision": lambda t: record_proposal_decision(
                self.instance, expected_core_root=ROOT, character_id="aria",
                proposal_id="pendiente", version=1, review_status=ReviewStatus.REJECTED,
                terminal=t),
            "new character": lambda t: import_concept(
                self.instance, expected_core_root=ROOT, character_id="nueva", version=1,
                input_path=self.root / "concepto.md", terminal=t),
        }
        for name, operation in operations.items():
            with self.subTest(name):
                terminal = FakeTerminal()
                with self.assertRaises(CharacterError) as ctx:
                    operation(terminal)
                self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        self.assertEqual(self.characters(), before)
        update_lock.unlink()
        self.assertTrue(self.update().updated)

    def test_an_update_started_during_a_character_write_waits_for_nothing(self):
        # A character write that took its lock first makes the update fail, not merge.
        self.closed_round()
        from core.runtime import character as character_module
        real_lock = character_module._corpus_lock

        def racing(state_path, subject, guard=None):
            manager = real_lock(state_path, subject, guard=guard)

            class Wrapper:
                def __enter__(self_inner):
                    value = manager.__enter__()
                    with self.assertRaises(InstanceError) as ctx:
                        self.update()
                    self.assertEqual(ctx.exception.code, "CONFLICT")
                    return value

                def __exit__(self_inner, *exc):
                    return manager.__exit__(*exc)

            return Wrapper()

        effective = get_effective_composition(self.loaded_instance(), character_id="aria")
        with mock.patch.object(character_module, "_corpus_lock", racing):
            add_proposal(self.instance, expected_core_root=ROOT, character_id="aria", value={
                "proposal_id": "primero", "version": 1,
                "base_composition_sha256": effective.composition_sha256, "text": "P\n",
                "rationale": "R", "citations": [{"candidate_id": "normas", "version": 3}]})
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        self.assertTrue(self.update().updated)
        self.assertIsNotNone(self.loaded_instance().characters[0].state.view("primero", 1))


class FailureTest(UpdateCase):
    def setUp(self):
        super().setUp()
        self.closed_round()
        self.statics_before = self.statics()
        self.characters_before = self.characters()

    def assert_intact(self):
        self.assertEqual(self.statics(), self.statics_before)
        self.assertEqual(self.characters(), self.characters_before)
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        self.assertFalse(update_lock_path(self.instance).exists())

    def flaky_replace(self, failing):
        def replace(src, dst, *args, **kwargs):
            if failing(Path(src), Path(dst)):
                raise PermissionError("simulado")
            return REAL_REPLACE(src, dst, *args, **kwargs)
        return replace

    def test_validation_failure_leaves_nothing(self):
        with mock.patch.object(instance_module, "_check_preserved",
                               side_effect=InstanceError("INVALID_STATE", "simulado")):
            with self.assertRaises(InstanceError):
                self.update()
        self.assert_intact()
        self.assertEqual(self.siblings(), [])

    def test_write_failure_in_the_staging_leaves_nothing(self):
        def failing_open(*args, **kwargs):
            raise OSError("disco lleno simulado")

        with mock.patch.object(instance_module, "open", failing_open, create=True):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        self.assert_intact()
        self.assertEqual(self.siblings(), [])

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
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        backup = next(p for p in self.root.iterdir() if "update-backup" in p.name)
        self.assertIn(str(backup), ctx.exception.reason)
        self.assertEqual(self.characters(), self.characters_before)
        shutil.rmtree(self.instance)
        backup.rename(self.instance)
        self.assert_intact()

    def test_first_rename_fails(self):
        replace = self.flaky_replace(lambda s, d: "update-backup" in d.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        self.assert_intact()
        self.assertEqual(self.siblings(), [])

    def test_second_rename_fails_and_is_restored(self):
        replace = self.flaky_replace(lambda s, d: "update-staging" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("se ha restaurado la anterior", ctx.exception.reason)
        self.assert_intact()
        self.assertEqual(self.siblings(), [])

    def test_restore_failure_keeps_a_complete_backup(self):
        replace = self.flaky_replace(lambda s, d: "update-staging" in s.name
                                     or "update-backup" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        backup = next(p for p in self.root.iterdir() if "update-backup" in p.name)
        staging = next(p for p in self.root.iterdir() if "update-staging" in p.name)
        self.assertIn(str(backup), ctx.exception.reason)
        self.assertFalse(self.instance.exists())
        backup.rename(self.instance)
        self.assert_intact()
        shutil.rmtree(staging)

    def test_backup_removal_failure_is_reported_after_applying(self):
        real_rmtree = shutil.rmtree

        def rmtree(path, *args, **kwargs):
            if "update-backup" in Path(path).name:
                raise PermissionError("simulado")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(workspace_module.shutil, "rmtree", rmtree):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("se actualizó", ctx.exception.reason)
        self.assertEqual(self.loaded_instance().config.schema_version, 2)
        self.assertEqual(self.characters(), self.characters_before)
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
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        update_lock_path(self.instance).unlink()
        self.assertEqual(self.loaded_instance().config.schema_version, 2)


class NarrativeUpdateTest(UpdateCase):
    """7a: narrative/ is preserved byte for byte like characters/."""

    def setUp(self):
        super().setUp()
        create_topic(self.instance, expected_core_root=ROOT, character_id="aria",
                     topic_id="escena", title="Escena")
        self.post("respuesta-1")
        seed = self.root / "semilla.json"
        seed.write_bytes(json.dumps({
            "seed_id": "turno-1", "version": 1, "intent": "Responder", "tone": "Sereno",
            "beats": [], "details": [], "ooc_constraints": [], "pending_outcomes": []}).encode())
        import_human_seed(self.instance, expected_core_root=ROOT, topic_id="escena",
                          input_path=seed, terminal=FakeTerminal())
        loaded = self.loaded_instance()
        topic = loaded.topics[0].state
        character = loaded.characters[0].state
        sheet = character.draft_view(1).record
        draft = self.root / "borrador.json"
        draft.write_bytes(json.dumps({
            "draft_id": "turno-1", "version": 1, "seed_id": "turno-1", "seed_version": 1,
            "seed_sha256": topic.seed("turno-1", 1).seed_sha256,
            "context_sha256": context_sha256(topic.replay.context),
            "composition_sha256": sheet.composition_sha256, "sheet_version": 1,
            "sheet_sha256": sheet.draft_sha256,
            "citations": [{"candidate_id": "normas", "version": 3}],
            "publishable_text": "Post propio\n", "ooc_notes": [], "private_notes": [],
            "pending_outcomes": []}).encode())
        record = create_narrative_draft(self.instance, expected_core_root=ROOT,
                                        topic_id="escena", input_path=draft).draft.record
        publication = self.root / "publicacion.json"
        publication.write_bytes(json.dumps({
            "post_id": "propio-1", "draft_sha256": record.draft_sha256,
            "locator": "https://foro.example/t/9#p2", "observed_at": "2026-10-14T21:00:00+02:00",
            "published_text": "Post propio editado\n"}).encode())
        confirm_narrative_publication(self.instance, expected_core_root=ROOT, topic_id="escena",
                                      draft_id="turno-1", version=1, input_path=publication,
                                      terminal=FakeTerminal())

    def post(self, post_id, terminal=None):
        path = self.root / f"{post_id}.json"
        path.write_bytes(json.dumps({
            "post_id": post_id, "author_label": "otra persona",
            "locator": f"https://foro.example/t/9#{post_id}",
            "observed_at": "2026-10-14T20:00:00+02:00", "content": f"Texto de {post_id}\n"
        }).encode())
        return record_external_post(self.instance, expected_core_root=ROOT, topic_id="escena",
                                    input_path=path, terminal=terminal or FakeTerminal())

    def narrative(self):
        folder = self.instance / "narrative"
        return {p.relative_to(folder).as_posix(): p.read_bytes()
                for p in sorted(folder.rglob("*")) if p.is_file()}

    def statics(self):
        return {path: data for path, data in super().statics().items()
                if not path.startswith("narrative/")}

    def topics(self):
        return [(t.topic_root, t.state_revision, t.state) for t in self.loaded_instance().topics]

    def test_topics_survive_v1_to_v2_and_a_further_round(self):
        narrative, topics = self.narrative(), self.topics()
        self.assertEqual(topics[0][1], 5)
        self.closed_round()
        terminal = FakeTerminal()
        self.assertTrue(self.update(terminal).updated)
        self.assertIn("Personajes preservados: 1\nTemas narrativos preservados: 1\n"
                      "Esta acción reemplaza solo los archivos estáticos", terminal.output)
        self.assertEqual((self.narrative(), self.topics()), (narrative, topics))
        third = successor_dossier(self.root, "exp3", version="2026-10-20", edit=lambda t, d: t.replace(
            "Las del sur, del fuego.\n~~~~\n",
            'Las del sur, del fuego.\n~~~~\n\n### Fuente\nMetadatos: id="mares" | versión="1" | '
            'autoridad="Staff" | alcance="foro"\n~~~~ texto\nEl mar no tiene fondo.\n~~~~\n'))
        self.workspace = self.root / "ampliacion-3"
        value = new_candidate("mar", quote="El mar no tiene fondo.")
        value["citations"][0]["source_id"] = "mares"
        self.extend(dossier_dir=third)
        self.add(value)
        self.decide("mar")
        self.close()
        self.assertTrue(self.update().updated)
        self.assertEqual((self.narrative(), self.topics()), (narrative, topics))
        self.assertEqual(self.siblings(), [])
        # The topic goes on after the updates.
        self.assertEqual(self.post("respuesta-2").post.position, 3)

    def test_without_topics_the_prompt_has_no_topic_line(self):
        shutil.rmtree(self.instance / "narrative")
        self.closed_round()
        terminal = FakeTerminal()
        self.update(terminal)
        self.assertNotIn("Temas narrativos", terminal.output)

    def test_topic_locks_block_the_update(self):
        self.closed_round()
        topics = self.instance / "narrative" / "topics"
        for lock in (topics / "escena" / "state.json.lock", topics / ".nuevo.create.lock"):
            with self.subTest(lock=lock.name):
                lock.write_bytes(b"")
                terminal = FakeTerminal()
                with self.assertRaises(InstanceError) as ctx:
                    self.update(terminal)
                self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
                self.assertIn("un tema se está modificando", ctx.exception.reason)
                lock.unlink()
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        update_lock_path(self.instance).write_bytes(b"")
        with self.assertRaises(NarrativeError) as ctx:
            self.post("bloqueado")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        update_lock_path(self.instance).unlink()
        self.assertTrue(self.update().updated)

    def test_a_topic_change_during_the_prompt_is_a_conflict(self):
        self.closed_round()
        statics = self.statics()
        with self.assertRaises(InstanceError) as ctx:
            self.update(FakeTerminal(on_read=lambda: self.post("carrera")))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.statics(), statics)
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        self.assertEqual(self.siblings(), [])

    def test_an_update_applied_during_a_narrative_prompt_is_a_conflict(self):
        """REV7A-01: the update changes only statics; the narrative write must still stop."""
        self.closed_round()
        narrative = self.narrative()
        with self.assertRaises(NarrativeError) as ctx:
            self.post("durante", terminal=FakeTerminal(on_read=lambda: self.update()))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.loaded_instance().config.schema_version, 2)
        self.assertEqual(self.narrative(), narrative)
        self.assertEqual(self.post("despues").post.position, 3)

    def test_rollback_and_kept_backup_preserve_narrative(self):
        self.closed_round()
        narrative = self.narrative()
        replace = FailureTest.flaky_replace(self, lambda s, d: "update-staging" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            with self.assertRaises(InstanceError):
                self.update()
        self.assertEqual(self.narrative(), narrative)
        self.assertEqual(self.siblings(), [])
        replace = FailureTest.flaky_replace(self, lambda s, d: "update-staging" in s.name
                                            or "update-backup" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace):
            with self.assertRaises(InstanceError):
                self.update()
        backup = next(p for p in self.root.iterdir() if "update-backup" in p.name)
        staging = next(p for p in self.root.iterdir() if "update-staging" in p.name)
        backup.rename(self.instance)
        shutil.rmtree(staging)
        self.assertEqual(self.narrative(), narrative)
        self.assertTrue(self.update().updated)
        self.assertEqual(self.narrative(), narrative)


class InstructionsAxisTest(UpdateCase):
    """7b: the corpus update keeps whichever instructions the instance has, byte for byte."""

    def instructions_bytes(self):
        return {name: (self.instance / name).read_bytes() if (self.instance / name).exists()
                else None for name in ("AGENTS.md", "CLAUDE.md", "work/instructions.json")}

    def test_v1_instructions_survive_v1_to_v2_corpus(self):
        before = self.instructions_bytes()
        model = self.loaded_instance().instructions
        self.closed_round()
        self.assertTrue(self.update().updated)
        after = self.loaded_instance()
        self.assertEqual((self.instructions_bytes(), after.instructions, after.config.schema_version),
                         (before, model, 2))
        self.assertIsNone(before["work/instructions.json"])

    def test_v2_instructions_survive_two_corpus_rounds_and_a_rollback(self):
        self.assertTrue(update_instance_instructions(self.instance, core_root=ROOT,
                                                     terminal=FakeTerminal()).updated)
        before = self.instructions_bytes()
        model = self.loaded_instance().instructions
        characters = self.characters()
        self.closed_round()
        replace_calls = FailureTest.flaky_replace(self, lambda s, d: "update-staging" in s.name)
        with mock.patch.object(instance_module.os, "replace", replace_calls):
            with self.assertRaises(InstanceError):
                self.update()
        self.assertEqual((self.instructions_bytes(), self.loaded_instance().config.schema_version),
                         (before, 1))
        self.assertTrue(self.update().updated)
        integrity = json.loads((self.instance / "work" / "integrity.json").read_bytes())
        self.assertEqual(integrity["schema_version"], 2)
        self.assertIn("work/instructions.json", [f["path"] for f in integrity["files"]])
        third = successor_dossier(self.root, "exp3", version="2026-10-20", edit=lambda t, d: t.replace(
            "Las del sur, del fuego.\n~~~~\n",
            'Las del sur, del fuego.\n~~~~\n\n### Fuente\nMetadatos: id="mares" | versión="1" | '
            'autoridad="Staff" | alcance="foro"\n~~~~ texto\nEl mar no tiene fondo.\n~~~~\n'))
        self.workspace = self.root / "ampliacion-3"
        value = new_candidate("mar", quote="El mar no tiene fondo.")
        value["citations"][0]["source_id"] = "mares"
        self.extend(dossier_dir=third)
        self.add(value)
        self.decide("mar")
        self.close()
        self.assertTrue(self.update().updated)
        after = self.loaded_instance()
        self.assertEqual((self.instructions_bytes(), after.instructions, self.characters()),
                         (before, model, characters))
        self.assertEqual(self.siblings(), [])
        # Already v2: the instructions update stays a no-op on a schema 2 instance.
        self.assertFalse(update_instance_instructions(self.instance, core_root=ROOT,
                                                      terminal=FakeTerminal()).updated)

    def test_each_update_conflicts_when_the_other_completes_during_its_prompt(self):
        self.closed_round()
        migrate = lambda: update_instance_instructions(self.instance, core_root=ROOT,  # noqa: E731
                                                       terminal=FakeTerminal())
        with self.assertRaises(InstanceError) as ctx:
            self.update(FakeTerminal(on_read=migrate))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        after = self.loaded_instance()
        self.assertEqual((after.config.schema_version, after.instructions.version), (1, 2))
        # REV7B-01: the round prepared on the v1 manifest still applies after the migration,
        # with a new confirmation, and keeps the v2 instructions byte for byte.
        migrated = self.instructions_bytes()
        terminal = FakeTerminal()
        self.assertTrue(self.update(terminal).updated)
        self.assertIn("ACTUALIZAR-INSTANCIA foro-neutral r2", terminal.output)
        after = self.loaded_instance()
        self.assertEqual((after.config.schema_version, after.instructions.version,
                          self.instructions_bytes()), (2, 2, migrated))
        self.assertEqual(self.siblings(), [])

    def test_a_round_prepared_on_v1_needs_the_same_static_files(self):
        self.closed_round()
        update_instance_instructions(self.instance, core_root=ROOT, terminal=FakeTerminal())
        legacy = instance_module._legacy_manifest_sha256
        with mock.patch.object(instance_module, "_legacy_manifest_sha256",
                               lambda instance, static: ()):
            with self.assertRaises(InstanceError) as ctx:
                self.update()
        self.assertIn("snapshot base", ctx.exception.reason)
        # The rebuilt manifest is exactly the one the workspace bound.
        loaded = self.loaded_instance()
        files = {path: (self.instance / path).read_bytes()
                 for path in ("instance.json", "work/integrity.json", "AGENTS.md", "CLAUDE.md",
                              "corpus/state.json", "work/instructions.json",
                              *(f.path for f in loaded.config.dossier_files))}
        base = self.loaded().config.base_instance
        self.assertEqual(legacy(loaded, files), (base.integrity_sha256,))
        self.assertTrue(self.update().updated)

    def test_the_instructions_update_conflicts_when_the_corpus_update_completes(self):
        self.closed_round()
        with self.assertRaises(InstanceError) as ctx:
            update_instance_instructions(self.instance, core_root=ROOT,
                                         terminal=FakeTerminal(on_read=lambda: self.update()))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        after = self.loaded_instance()
        self.assertEqual((after.config.schema_version, after.instructions.version), (2, 1))
        self.assertTrue(update_instance_instructions(self.instance, core_root=ROOT,
                                                     terminal=FakeTerminal()).updated)
        self.assertEqual(self.loaded_instance().config.schema_version, 2)


class UpdateCliTest(UpdateCase):
    def test_update_and_history_through_the_cli(self):
        code, out, _ = run("instance", "corpus", "history", "--instance", str(self.instance))
        legacy = closed_corpus_of(self.loaded_instance()).current
        line1 = (f"ronda 1 | LEGACY_V1 | expediente=\"2026-10-11\" | "
                 f"dossier_sha256={legacy.dossier.snapshot_sha256} | "
                 f"snapshot={legacy.snapshot_sha256} | padre=null | "
                 f"candidatos={legacy.candidate_count} (+{legacy.candidate_count}) | "
                 f"decisiones={legacy.decision_count} (+{legacy.decision_count})")
        self.assertEqual((code, out), (0, line1 + "\n"))
        self.closed_round()
        argv = ["instance", "update", "--instance", str(self.instance), "--workspace",
                str(self.workspace)]
        code, out, _ = run("--json", *argv)
        self.assertEqual((code, json.loads(out)["message"]), (3, (
            "la actualización de una instancia no admite --json: ejecuta el comando en tu "
            "terminal y responde a la confirmación")))
        code, out, _ = run(*argv, stdin="ACTUALIZAR-INSTANCIA foro-neutral r2 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.loaded_instance().config.schema_version, 1)
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            code, out, _ = run(*argv)
            snapshot = self.loaded_instance().config.corpus.snapshot_sha256
            self.assertEqual((code, out), (0, (
                f"Instancia actualizada: foro-neutral | snapshot {legacy.snapshot_sha256} -> "
                f"{snapshot} | expediente 2026-10-14 | personajes 1.\n")))
            code, out, _ = run(*argv)
            self.assertEqual(out, (f"Instancia ya actualizada: foro-neutral | snapshot {snapshot} "
                                   "| expediente 2026-10-14 | personajes 1.\n"))
        code, out, _ = run("--json", "instance", "corpus", "history", "--instance",
                           str(self.instance))
        payload = json.loads(out)
        self.assertEqual((payload["action"], payload["current_snapshot_sha256"]),
                         ("instance.corpus.history", snapshot))
        self.assertEqual([(s["ordinal"], s["format"], s["candidate_delta"], s["decision_delta"],
                           s["parent_snapshot_sha256"]) for s in payload["snapshots"]],
                         [(1, "LEGACY_V1", legacy.candidate_count, legacy.decision_count, None),
                          (2, "ADDITIVE_V2", 1, 1, legacy.snapshot_sha256)])
        self.assertEqual(set(payload["snapshots"][0]), {
            "candidate_count", "candidate_delta", "corpus_revision", "decision_count",
            "decision_delta", "dossier_snapshot_sha256", "dossier_version", "format", "ordinal",
            "parent_snapshot_sha256", "snapshot_sha256"})
        code, out, _ = run("instance", "status", "--instance", str(self.instance))
        self.assertEqual(code, 0)
        for name in ("reopen", "supersede", "retire", "publish"):
            self.assertEqual(run("instance", name, "--instance", "x")[0], 2)


if __name__ == "__main__":
    unittest.main()
