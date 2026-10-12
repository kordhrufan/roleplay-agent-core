import copy
import dataclasses
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.manual import load_manual_dossier
from core.review.models import ReviewStatus
from core.runtime import persistence
from core.runtime.assimilation import (
    AssimilationCandidate,
    AssimilationDomain,
    AssimilationError,
    CandidateAddResult,
    CandidateCitation,
    CandidateClass,
    DossierSection,
    _candidate_record,
    add_candidate,
    decode_candidate_state,
    load_dossier,
    parse_candidate_input,
)
from core.runtime.persistence import canonical_json_bytes, encode_state, load_state
from core.runtime.workspace import CORPUS_STATE, WorkspaceError, create_workspace, load_workspace

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
RESPECT = "Trata con respeto al resto de participantes"
MANUAL = {"dossier_section": "forum_rules", "source_id": "manual-foro", "source_version": "1",
          "declared_passage": "Convivencia"}
WORLD = {"dossier_section": "setting", "source_id": "mundo-base", "source_version": "2",
         "declared_passage": None}


def candidate_input(**overrides) -> dict:
    value = {"candidate_id": "convivencia-respeto", "version": 1, "domain": "RULES",
             "class": "LITERAL", "text": RESPECT, "scope": "foro",
             "citations": [dict(MANUAL, quote=RESPECT)]}
    value.update(overrides)
    return value


class DossierCase(unittest.TestCase):
    dossier = None

    @classmethod
    def setUpClass(cls):
        cls.dossier = load_dossier(FIXTURE)

    def parse(self, **overrides) -> AssimilationCandidate:
        return parse_candidate_input(candidate_input(**overrides), dossier=self.dossier)

    def invalid(self, **overrides) -> AssimilationError:
        with self.assertRaises(AssimilationError) as ctx:
            self.parse(**overrides)
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        return ctx.exception


class ModelTest(DossierCase):
    def citation(self, **overrides) -> CandidateCitation:
        fields = dict(dossier_section=DossierSection.FORUM_RULES, source_id="s", source_version="1",
                      source_sha256="a" * 64, declared_passage=None, start=0, end=3, quote="abc")
        fields.update(overrides)
        return CandidateCitation(**fields)

    def test_enums(self):
        self.assertEqual([d.value for d in AssimilationDomain], ["RULES", "WORLD"])
        self.assertEqual([c.value for c in CandidateClass],
                         ["LITERAL", "INTERPRETATION", "PROPOSAL", "UNCERTAINTY"])

    def test_citation_validation(self):
        self.citation()
        for overrides in (dict(dossier_section="forum_rules"), dict(source_sha256="A" * 64),
                          dict(start=-1, end=2), dict(end=4), dict(start=True), dict(quote="  "),
                          dict(source_id=" s"), dict(declared_passage="")):
            with self.subTest(overrides=str(overrides)):
                with self.assertRaises(AssimilationError):
                    self.citation(**overrides)

    def test_candidate_is_immutable_and_hashed(self):
        candidate = self.parse()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.text = "otro"
        record = _candidate_record(candidate, include_hash=False)
        expected = hashlib.sha256(canonical_json_bytes(record, pretty=False)).hexdigest()
        self.assertEqual(candidate.candidate_sha256, expected)
        self.assertIs(candidate.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)

    def test_citation_and_result_are_immutable(self):
        citation = self.citation()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            citation.start = 1
        result = CandidateAddResult(self.parse(), True, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.created = False

    def test_only_pending_status(self):
        candidate = self.parse()
        with self.assertRaises(AssimilationError):
            AssimilationCandidate(candidate.candidate_id, 1, candidate.domain,
                                  candidate.candidate_class, candidate.text, candidate.scope,
                                  candidate.citations, ReviewStatus.APPROVED)

    def test_field_validation(self):
        for overrides in (dict(candidate_id="Convivencia"), dict(candidate_id="a_b"),
                          dict(version=0), dict(version=True), dict(version="1"),
                          dict(domain="rules"), dict(**{"class": "OPINION"}), dict(text=" "),
                          dict(scope=" foro"), dict(scope="foro\n")):
            with self.subTest(overrides=str(overrides)):
                self.invalid(**overrides)


class InputTest(DossierCase):
    def test_literal_offsets_are_computed(self):
        candidate = self.parse()
        citation = candidate.citations[0]
        literal = self.dossier.sections[0].sources[0].literal_text
        self.assertEqual(literal[citation.start:citation.end], RESPECT)
        self.assertEqual(citation.source_sha256, self.dossier.sections[0].sources[0].source_ref.sha256)

    def test_exact_input_keys(self):
        for value in ([], "x", {**candidate_input(), "extra": 1},
                      {k: v for k, v in candidate_input().items() if k != "scope"}):
            with self.subTest(value=str(value)[:40]):
                with self.assertRaises(AssimilationError):
                    parse_candidate_input(value, dossier=self.dossier)
        for citation in ({**MANUAL, "quote": RESPECT, "start": 0},
                         {**MANUAL, "quote": RESPECT, "source_sha256": "a" * 64},
                         {k: v for k, v in MANUAL.items() if k != "declared_passage"} | {"quote": RESPECT},
                         "texto"):
            with self.subTest(citation=str(citation)[:50]):
                self.invalid(citations=[citation])
        self.invalid(citations=[])
        self.invalid(citations={})

    def test_multiline_quote(self):
        text = "- Llanura central\n- Costa norte\n"
        candidate = self.parse(candidate_id="regiones", domain="WORLD", text=text,
                               citations=[dict(WORLD, quote=text)])
        self.assertEqual(candidate.citations[0].quote, text)

    def test_quote_must_match_exactly(self):
        for quote in (RESPECT.lower(), RESPECT + ".", " " + RESPECT, "Trata  con respeto",
                      "No existe"):
            with self.subTest(quote=quote):
                error = self.invalid(text=quote, citations=[dict(MANUAL, quote=quote)])
                self.assertIn("no aparece", error.reason)

    def test_repeated_quote_needs_occurrence(self):
        quote = "post"  # appears in "respeta el turno de cada post." only once
        self.parse(candidate_id="x", **{"class": "INTERPRETATION"}, text="t",
                   citations=[dict(MANUAL, quote=quote)])
        error = self.invalid(candidate_id="x", **{"class": "INTERPRETATION"}, text="t",
                             citations=[dict(MANUAL, quote="re")])
        self.assertIn("veces", error.reason)
        self.assertIn("occurrence", error.reason)
        self.assertIn("línea", error.reason)
        literal = self.dossier.sections[0].sources[0].literal_text
        starts = [i for i in range(len(literal)) if literal.startswith("re", i)]
        second = self.parse(candidate_id="x", **{"class": "INTERPRETATION"}, text="t",
                            citations=[dict(MANUAL, quote="re", occurrence=2)])
        self.assertEqual(second.citations[0].start, starts[1])
        error = self.invalid(candidate_id="x", **{"class": "INTERPRETATION"}, text="t",
                             citations=[dict(MANUAL, quote="re", occurrence=len(starts) + 1)])
        self.assertIn(str(len(starts)), error.reason)
        for bad in (0, -1, True, "2"):
            with self.subTest(occurrence=bad):
                self.invalid(candidate_id="x", **{"class": "INTERPRETATION"}, text="t",
                             citations=[dict(MANUAL, quote="re", occurrence=bad)])

    def test_overlapping_occurrences_are_counted(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copytree(FIXTURE, root / "exp")
        (root / "exp" / "materials" / "manual-foro.md").write_bytes(b"aaaa\n")
        dossier = load_dossier(root / "exp")
        value = candidate_input(candidate_id="x", text="t", citations=[dict(MANUAL, quote="aa")],
                                **{"class": "INTERPRETATION"})
        with self.assertRaises(AssimilationError) as ctx:
            parse_candidate_input(value, dossier=dossier)
        self.assertIn("3 veces", ctx.exception.reason)
        value["citations"][0]["occurrence"] = 2
        self.assertEqual(parse_candidate_input(value, dossier=dossier).citations[0].start, 1)

    def test_file_crlf_and_unicode(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copytree(FIXTURE, root / "exp")
        (root / "exp" / "materials" / "manual-foro.md").write_bytes(
            "Línea uno\r\nÑandú y acentos: ¿sí?\r\n".encode("utf-8"))
        dossier = load_dossier(root / "exp")
        quote = "uno\r\nÑandú"
        candidate = parse_candidate_input(candidate_input(text=quote, citations=[dict(MANUAL, quote=quote)]),
                                          dossier=dossier)
        self.assertEqual(candidate.citations[0].start, len("Línea "))
        with self.assertRaises(AssimilationError):
            parse_candidate_input(candidate_input(text="uno\nÑandú",
                                                  citations=[dict(MANUAL, quote="uno\nÑandú")]),
                                  dossier=dossier)

    def test_declared_passage_must_match_exactly(self):
        self.invalid(citations=[dict(MANUAL, declared_passage=None, quote=RESPECT)])
        self.invalid(citations=[dict(MANUAL, declared_passage="Fichas", quote=RESPECT)])
        other = dict(MANUAL, dossier_section="character_creation", declared_passage="Fichas")
        candidate = self.parse(citations=[dict(other, quote=RESPECT)])
        self.assertIs(candidate.citations[0].dossier_section, DossierSection.CHARACTER_CREATION)
        self.invalid(citations=[dict(MANUAL, source_version="2", quote=RESPECT)])

    def test_domain_matches_section(self):
        rules_sections = {
            "forum_rules": (MANUAL, RESPECT),
            "character_creation": (dict(MANUAL, dossier_section="character_creation",
                                        declared_passage="Fichas"), RESPECT),
            "staff_review": ({"dossier_section": "staff_review", "source_id": "revision-staff",
                              "source_version": "1", "declared_passage": None}, "Las fichas"),
            "platform_format": ({"dossier_section": "platform_format",
                                 "source_id": "formato-posts", "source_version": "1",
                                 "declared_passage": "Formato"}, "tercera persona"),
        }
        for section, (source, quote) in rules_sections.items():
            with self.subTest(section=section):
                self.parse(text=quote, citations=[dict(source, quote=quote)])
                with self.assertRaises(AssimilationError):
                    self.parse(domain="WORLD", text=quote, citations=[dict(source, quote=quote)])
        self.parse(domain="WORLD", text="Mundo base", citations=[dict(WORLD, quote="Mundo base")])
        self.invalid(text="Mundo base", citations=[dict(WORLD, quote="Mundo base")])

    def test_optional_rule_sections_have_no_sources_here(self):
        for section in ("combat_system", "ability_technique_creation"):
            with self.subTest(section=section):
                self.invalid(citations=[{"dossier_section": section, "source_id": "x",
                                         "source_version": "1", "declared_passage": None,
                                         "quote": "x"}])

    def test_loose_material_is_not_citable(self):
        for section in ("loose_material", None):
            with self.subTest(section=section):
                self.invalid(citations=[{"dossier_section": section, "source_id": "aviso-staff",
                                         "source_version": "1", "declared_passage": None,
                                         "quote": "Aviso"}])

    def test_literal_rules(self):
        self.invalid(text="Otro texto")
        self.invalid(citations=[dict(MANUAL, quote=RESPECT),
                                dict(MANUAL, quote="respeta el turno")])

    def test_other_classes_allow_free_text_and_several_citations(self):
        for cls in ("INTERPRETATION", "PROPOSAL", "UNCERTAINTY"):
            with self.subTest(cls=cls):
                candidate = self.parse(**{"class": cls}, text="Conclusión propia.\nCon saltos.",
                                       citations=[dict(MANUAL, quote=RESPECT),
                                                  dict(MANUAL, quote="respeta el turno")])
                self.assertEqual(len(candidate.citations), 2)
                self.assertEqual(candidate.requires_confirmation, cls == "UNCERTAINTY")

    def test_duplicate_citation_rejected(self):
        self.invalid(**{"class": "INTERPRETATION"}, text="t",
                     citations=[dict(MANUAL, quote=RESPECT), dict(MANUAL, quote=RESPECT)])


class StoreTest(DossierCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copytree(FIXTURE, root / "exp")
        self.workspace = root / "ws"
        create_workspace(load_manual_dossier(root / "exp"), dossier_dir=root / "exp",
                         workspace=self.workspace, core_root=ROOT)
        self.state = self.workspace / CORPUS_STATE
        self.loaded = load_workspace(self.workspace)

    def add(self, revision: int, **overrides):
        return add_candidate(self.state, dossier=self.loaded.dossier, expected_revision=revision,
                             value=candidate_input(**overrides))

    def test_persisted_shape(self):
        result = self.add(0)
        self.assertEqual((result.created, result.corpus_revision), (True, 1))
        revision, content = load_state(self.state)
        self.assertEqual(revision, 1)
        self.assertEqual(content["closure"], None)
        self.assertEqual(content["decisions"], [])
        record = content["candidates"][0]
        self.assertEqual(set(record), {"candidate_id", "candidate_sha256", "citations", "class",
                                       "domain", "review_status", "scope", "text", "version"})
        self.assertEqual(set(record["citations"][0]),
                         {"declared_passage", "dossier_section", "end", "quote", "source_id",
                          "source_sha256", "source_version", "start"})
        self.assertNotIn("occurrence", json.dumps(record))
        self.assertEqual(record["review_status"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(load_workspace(self.workspace).candidates, (result.candidate,))

    def test_retry_is_idempotent_without_writes(self):
        self.add(0)
        before = (self.state.read_bytes(), self.state.stat().st_mtime_ns)
        result = self.add(1)
        self.assertEqual((result.created, result.corpus_revision), (False, 1))
        self.assertEqual(before, (self.state.read_bytes(), self.state.stat().st_mtime_ns))

    def test_versions(self):
        self.add(0)
        with self.assertRaises(AssimilationError) as ctx:
            self.add(1, text="Otro", **{"class": "INTERPRETATION"})
        self.assertEqual(ctx.exception.code, "CONFLICT")
        with self.assertRaises(AssimilationError) as ctx:
            self.add(1, version=3)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        with self.assertRaises(AssimilationError) as ctx:
            self.add(1, version=2)  # same payload as v1
        self.assertEqual(ctx.exception.code, "CONFLICT")
        with self.assertRaises(AssimilationError) as ctx:
            self.add(1, candidate_id="nuevo", version=2)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        second = self.add(1, version=2, scope="fichas")
        self.assertEqual(second.corpus_revision, 2)
        versions = [c.version for c in load_workspace(self.workspace).candidates]
        self.assertEqual(versions, [1, 2])

    def test_stale_revision_conflicts(self):
        self.add(0)
        with self.assertRaises(AssimilationError) as ctx:
            self.add(0, candidate_id="otro")
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_failed_replace_keeps_previous_state(self):
        before = self.state.read_bytes()
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(AssimilationError) as ctx:
                self.add(0)
        self.assertEqual(ctx.exception.code, "IO")
        self.assertEqual(self.state.read_bytes(), before)

    def tamper(self, change) -> None:
        revision, content = load_state(self.state)
        content = copy.deepcopy(content)
        change(content)
        self.state.write_bytes(encode_state(content, revision=revision))
        with self.assertRaises(WorkspaceError) as ctx:
            load_workspace(self.workspace)
        self.assertEqual(ctx.exception.code, "INVALID_STATE")

    def test_manipulated_state_fails_on_load(self):
        self.add(0)
        original = self.state.read_bytes()
        changes = {
            "text": lambda c: c["candidates"][0].update(text="Otro"),
            "hash": lambda c: c["candidates"][0].update(candidate_sha256="0" * 64),
            "offset": lambda c: c["candidates"][0]["citations"][0].update(start=1, end=44),
            "source hash": lambda c: c["candidates"][0]["citations"][0].update(source_sha256="0" * 64),
            "status": lambda c: c["candidates"][0].update(review_status="APPROVED"),
            "extra key": lambda c: c["candidates"][0].update(nota="x"),
            "version gap": lambda c: c["candidates"][0].update(version=2),
            "decisions": lambda c: c.update(decisions=[{}]),
            "closure": lambda c: c.update(closure={}),
        }
        for name, change in changes.items():
            with self.subTest(name):
                self.tamper(change)
                self.state.write_bytes(original)
        load_workspace(self.workspace)

    def test_decode_requires_contiguous_ascending_versions(self):
        first = _candidate_record(self.parse(), include_hash=True)
        second = _candidate_record(self.parse(version=2, scope="fichas"), include_hash=True)
        state = decode_candidate_state({"candidates": [first, second], "closure": None,
                                        "decisions": []}, dossier=self.dossier, revision=2)
        self.assertEqual([c.version for c in state.candidates], [1, 2])
        for records in ([second], [second, first], [first, first]):
            with self.subTest(order=[r["version"] for r in records]):
                with self.assertRaises(AssimilationError):
                    decode_candidate_state({"candidates": records, "closure": None,
                                            "decisions": []}, dossier=self.dossier, revision=2)


if __name__ == "__main__":
    unittest.main()
