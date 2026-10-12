import copy
import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.character.models import (
    AppliedProposal,
    CharacterError,
    CharacterProposal,
    CharacterProposalDecision,
    CharacterState,
    ConceptRef,
    CorpusCandidateRef,
    EffectiveComposition,
    ProposalStatus,
    ProposalView,
    concept_root,
    decision_record,
    decode_character_state,
    encode_character_content,
    make_concept_version,
    make_proposal_decision,
    proposal_record,
)
from core.review.models import ReviewStatus
from core.runtime import assimilation, character as character_module
from core.runtime.assimilation import HumanConfirmationReceipt
from core.runtime.character import (
    add_proposal,
    get_effective_composition,
    get_proposal,
    import_concept,
    list_proposals,
    record_proposal_decision,
)
from core.runtime.instance import (
    InstanceError,
    approved_corpus,
    create_instance,
    load_instance,
)
from core.runtime.persistence import canonical_json_bytes, encode_state, load_state
from tests.instance_support import ROOT, closed_workspace
from tests.test_assimilation_decisions import FakeTerminal

APPROVED, REJECTED = ReviewStatus.APPROVED, ReviewStatus.REJECTED
RECEIPT = HumanConfirmationReceipt("TTY_NONCE_V1", "a" * 64)
CANDIDATES = {("normas", 3): "1" * 64, ("mundo", 1): "2" * 64}
NOTICE = ("Esta decisión solo compone el diseño del personaje; no es aprobación de staff, "
          "aprendizaje, utilizabilidad, publicación ni canon.\n")


def sha(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value, pretty=False)).hexdigest()


def concept(version=1, text="# Aria\nExploradora.\n"):
    return make_concept_version(forum_id="foro", character_id="aria", version=version, text=text,
                                receipt=RECEIPT)


def ref(candidate_id="normas", version=3):
    return CorpusCandidateRef(candidate_id, version, CANDIDATES[(candidate_id, version)])


def proposal(base: EffectiveComposition, revision: int, proposal_id="ajuste", version=1,
             text="# Aria\nExploradora valiente.\n", rationale="Encaja con las normas.",
             citations=None):
    return CharacterProposal("aria", proposal_id, version, revision, base.concept,
                             base.composition_sha256, text, rationale,
                             (ref(),) if citations is None else citations)


def decide(item: CharacterProposal, revision: int, status=APPROVED):
    return make_proposal_decision(forum_id="foro", character_id="aria", proposal=item,
                                  decision_revision=revision, review_status=status,
                                  receipt=RECEIPT)


class Resolver:
    """Duck-typed resolver: only `candidate_sha256` is read."""

    def __call__(self, candidate_id, version):
        try:
            return mock.Mock(candidate_sha256=CANDIDATES[(candidate_id, version)])
        except KeyError:
            raise InstanceError("INVALID_STATE", f"{candidate_id} v{version} no es vigente")


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.c1 = concept()
        self.root = concept_root("aria", self.c1)

    def test_refs_validate(self):
        for args in ((0, "a" * 64), (1, "A" * 64), (True, "a" * 64), (1, "a" * 63)):
            with self.subTest(args=args):
                with self.assertRaises(CharacterError):
                    ConceptRef(*args)
        for args in (("Normas", 1, "a" * 64), ("normas", 0, "a" * 64), ("normas", 1, "x")):
            with self.subTest(args=args):
                with self.assertRaises(CharacterError):
                    CorpusCandidateRef(*args)

    def test_models_are_frozen(self):
        item = proposal(self.root, 2)
        for target, name in ((item, "text"), (self.root, "text"), (ref(), "version"),
                             (decide(item, 3), "review_status")):
            with self.subTest(type(target).__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(target, name, "x")

    def test_proposal_validation(self):
        cases = {
            "empty citations": dict(citations=()),
            "duplicate citation": dict(citations=(ref(), ref())),
            "empty text": dict(text=" \n"),
            "bom": dict(text="\ufeffhola"),
            "control": dict(text="hola\x07"),
            "nul": dict(rationale="a\x00b"),
            "empty rationale": dict(rationale=""),
            "bad id": dict(proposal_id="Ajuste"),
            "bad version": dict(version=0),
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    proposal(self.root, 2, **overrides)

    def test_hashes_follow_the_exact_formulas(self):
        for text in ("Ñandú «ü» 🌊\n", "línea\r\notra\r\n", "sin salto final"):
            with self.subTest(text=text):
                c1 = concept(text=text)
                root = concept_root("aria", c1)
                c_ref = {"concept_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "version": 1}
                self.assertEqual(root.composition_sha256,
                                 sha({"character_id": "aria", "concept": c_ref, "text": text}))
                item = proposal(root, 2, text=text + "x", rationale=text)
                core = {"base_composition_sha256": root.composition_sha256,
                        "citations": [{"candidate_id": "normas", "candidate_sha256": "1" * 64,
                                       "version": 3}],
                        "concept": c_ref, "created_revision": 2, "proposal_id": "ajuste",
                        "rationale": text, "text": text + "x",
                        "utf8_size": len((text + "x").encode()), "version": 1}
                self.assertEqual(item.proposal_sha256, sha(core))
                self.assertEqual(item.result_composition_sha256, sha({
                    "base_composition_sha256": root.composition_sha256, "character_id": "aria",
                    "concept": c_ref, "proposal": {"proposal_id": "ajuste",
                                                   "proposal_sha256": item.proposal_sha256,
                                                   "version": 1},
                    "text": text + "x"}))
                self.assertEqual(proposal_record(item), {
                    **core, "proposal_sha256": item.proposal_sha256,
                    "result_composition_sha256": item.result_composition_sha256})

    def test_citation_order_is_part_of_the_identity(self):
        a = proposal(self.root, 2, citations=(ref(), ref("mundo", 1)))
        b = proposal(self.root, 2, citations=(ref("mundo", 1), ref()))
        self.assertNotEqual(a.proposal_sha256, b.proposal_sha256)

    def test_decision_validation_and_evidence(self):
        item = proposal(self.root, 2)
        decision = decide(item, 3)
        record = decision_record(decision)
        self.assertEqual(set(record), {"base_composition_sha256", "decision_id",
                                       "decision_revision", "evidence", "proposal_id",
                                       "proposal_sha256", "proposal_version", "receipt",
                                       "result_composition_sha256", "review_status"})
        self.assertEqual(record["decision_id"], "proposal:ajuste:v1")
        self.assertEqual(record["evidence"]["locator"],
                         "instance://foro/characters/aria/proposals/ajuste/v1/decision")
        self.assertEqual(record["evidence"]["source_id"],
                         "human-proposal-decision:aria:ajuste:v1")
        self.assertEqual(record["evidence"]["section_or_passage"], "proposal:ajuste:v1")
        payload = {k: v for k, v in record.items() if k != "evidence"}
        payload["character_id"] = "aria"
        self.assertEqual(record["evidence"]["sha256"], sha(payload))
        for status in (ReviewStatus.PENDING_HUMAN_REVIEW, "APPROVED"):
            with self.subTest(status=status):
                with self.assertRaises(CharacterError):
                    decide(item, 3, status)
        with self.assertRaises(CharacterError):
            dataclasses.replace(decision, decision_id="proposal:otro:v1")

    def test_views_and_applied_steps_must_be_coherent(self):
        item = proposal(self.root, 2)
        approved, rejected = decide(item, 3), decide(item, 3, REJECTED)
        AppliedProposal(item, approved)
        for bad in (rejected, decide(proposal(self.root, 2, text="otro"), 3)):
            with self.assertRaises(CharacterError):
                AppliedProposal(item, bad)
        ProposalView(item, ProposalStatus.APPROVED, approved, True, self.root)
        for args in ((ProposalStatus.APPROVED, None, False),
                     (ProposalStatus.REJECTED, approved, False),
                     (ProposalStatus.PENDING, approved, False),
                     (ProposalStatus.OBSOLETE, None, True),
                     (ProposalStatus.REJECTED, rejected, True)):
            with self.subTest(args=args):
                with self.assertRaises(CharacterError):
                    ProposalView(item, *args, self.root)
        self.assertEqual([s.value for s in ProposalStatus],
                         ["PENDING", "APPROVED", "REJECTED", "OBSOLETE"])

    def test_views_reject_a_foreign_decision_or_base(self):
        a = proposal(self.root, 2, "a")
        b = proposal(self.root, 3, "b")
        a_other_text = proposal(self.root, 2, "a", text="Otro texto\n")
        for decision in (decide(b, 4), decide(a_other_text, 3)):
            with self.subTest(decision=decision.proposal_key):
                with self.assertRaises(CharacterError):
                    ProposalView(a, ProposalStatus.APPROVED, decision, False, self.root)
        approved = CharacterState("aria", (self.c1,), (a,), (decide(a, 3),)).replay.effective
        c2 = concept(2, "Otro concepto\n")
        other_character = make_concept_version(forum_id="foro", character_id="otra", version=1,
                                               text=self.c1.text, receipt=RECEIPT)
        for base in (approved, concept_root("aria", c2),
                     concept_root("otra", other_character), "base"):
            with self.subTest(base=getattr(base, "composition_sha256", base)):
                with self.assertRaises(CharacterError):
                    ProposalView(a, ProposalStatus.PENDING, None, False, base)
        with self.assertRaises(CharacterError):
            ProposalView("a", ProposalStatus.PENDING, None, False, self.root)
        ProposalView(a, ProposalStatus.APPROVED, decide(a, 3), False, self.root)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.c1, self.c2 = concept(), concept(2, "# Aria\nSegunda versión.\n")
        self.root = concept_root("aria", self.c1)

    def chain(self):
        """c1 (r1), a v1 (r2), approve (r3), b v1 on a (r4), approve (r5)."""
        a = proposal(self.root, 2, "a", text="Texto A\n")
        da = decide(a, 3)
        after_a = CharacterState("aria", (self.c1,), (a,), (da,)).replay.effective
        b = proposal(after_a, 4, "b", text="Texto B")
        db = decide(b, 5)
        return a, da, b, db

    def test_root_and_two_chained_approvals(self):
        empty = CharacterState("aria", (self.c1,))
        self.assertEqual(empty.replay.effective, self.root)
        self.assertEqual(empty.revision, 1)
        a, da, b, db = self.chain()
        state = CharacterState("aria", (self.c1,), (a, b), (da, db))
        effective = state.replay.effective
        self.assertEqual((effective.text, effective.composition_sha256),
                         ("Texto B", b.result_composition_sha256))
        self.assertEqual([s.proposal for s in effective.applied_proposals], [a, b])
        self.assertEqual(b.base_composition_sha256, a.result_composition_sha256)
        self.assertEqual([(v.status, v.applied_to_effective) for v in state.replay.views],
                         [(ProposalStatus.APPROVED, True)] * 2)
        self.assertEqual(state.view("b", 1).base.text, "Texto A\n")

    def test_new_concept_restarts_the_chain_and_keeps_history(self):
        a, da, b, db = self.chain()
        pending = proposal(CharacterState("aria", (self.c1,), (a, b), (da, db)).replay.effective,
                           6, "c")
        state = CharacterState("aria", (self.c1, self.c2), (a, b, pending), (da, db))
        self.assertEqual(state.revision, 7)
        self.assertEqual(state.replay.effective, concept_root("aria", self.c2))
        self.assertEqual([(v.status, v.applied_to_effective) for v in state.replay.views],
                         [(ProposalStatus.APPROVED, False), (ProposalStatus.APPROVED, False),
                          (ProposalStatus.OBSOLETE, False)])

    def test_parallel_and_new_versions_become_obsolete(self):
        a, b = proposal(self.root, 2, "a"), proposal(self.root, 3, "b", text="Otra\n")
        state = CharacterState("aria", (self.c1,), (a, b))
        self.assertEqual([v.status for v in state.replay.views], [ProposalStatus.PENDING] * 2)
        approved = CharacterState("aria", (self.c1,), (a, b), (decide(a, 4),))
        self.assertEqual([v.status for v in approved.replay.views],
                         [ProposalStatus.APPROVED, ProposalStatus.OBSOLETE])
        a2 = proposal(self.root, 4, "a", 2, text="A dos\n")
        versions = CharacterState("aria", (self.c1,), (a, b, a2))
        self.assertEqual([v.status for v in versions.replay.views],
                         [ProposalStatus.OBSOLETE, ProposalStatus.PENDING,
                          ProposalStatus.PENDING])
        rejected_old = CharacterState("aria", (self.c1,), (a, b, a2), (decide(a, 5, REJECTED),))
        self.assertEqual(rejected_old.replay.effective, self.root)
        self.assertEqual(rejected_old.view("a", 1).status, ProposalStatus.REJECTED)
        self.assertEqual(rejected_old.view("b", 1).status, ProposalStatus.PENDING)

    def test_invalid_logs_are_rejected(self):
        a = proposal(self.root, 2, "a")
        a2 = proposal(self.root, 3, "a", 2, text="A dos\n")
        b = proposal(self.root, 3, "b")
        stale = proposal(self.root, 4, "c")
        cases = {
            "approval of an old version": ((self.c1,), (a, a2), (decide(a, 4),)),
            "approval with an old base": ((self.c1,), (a, b, stale),
                                          (decide(a, 4), decide(stale, 5))),
            "decision before its proposal": ((self.c1,), (proposal(self.root, 3, "a"),),
                                             (decide(proposal(self.root, 3, "a"), 2),)),
            "duplicate revision": ((self.c1,), (a, proposal(self.root, 2, "b")), ()),
            "revision out of range": ((self.c1,), (proposal(self.root, 5, "a"),), ()),
            "proposal before any concept": ((self.c1,), (proposal(self.root, 1, "a"),), ()),
            "wrong concept": ((self.c1, self.c2), (proposal(self.root, 3, "a"),), ()),
            "version skip": ((self.c1,), (proposal(self.root, 2, "a", 2),), ()),
            "two decisions": ((self.c1,), (a,), (decide(a, 3, REJECTED), decide(a, 4))),
            "decision for another text": ((self.c1,), (a,),
                                          (decide(proposal(self.root, 2, "a", text="x"), 3),)),
            "proposals out of order": ((self.c1,), (b, a), ()),
            "other character": ((self.c1,), (dataclasses.replace(a, character_id="otro"),), ()),
        }
        for name, (concepts, proposals, decisions) in cases.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    CharacterState("aria", concepts, proposals, decisions)


class CodecTest(unittest.TestCase):
    def setUp(self):
        c1 = concept()
        root = concept_root("aria", c1)
        a = proposal(root, 2, "a", citations=(ref(), ref("mundo", 1)))
        b = proposal(root, 3, "b")
        self.state = CharacterState("aria", (c1,), (a, b), (decide(a, 4), ))
        self.content = encode_character_content(self.state)

    def decode(self, content, revision=4, resolver=Resolver()):
        return decode_character_state(content, forum_id="foro", revision=revision,
                                      candidate_resolver=resolver)

    def test_round_trip_and_shapes(self):
        self.assertEqual(self.decode(self.content), self.state)
        self.assertEqual(set(self.content["proposals"][0]), {
            "base_composition_sha256", "citations", "concept", "created_revision", "proposal_id",
            "proposal_sha256", "rationale", "result_composition_sha256", "text", "utf8_size",
            "version"})
        self.assertEqual(self.content["proposals"][0]["citations"], [
            {"candidate_id": "normas", "candidate_sha256": "1" * 64, "version": 3},
            {"candidate_id": "mundo", "candidate_sha256": "2" * 64, "version": 1}])
        self.assertNotIn("effective", self.content)
        for record in self.content["proposals"]:
            self.assertNotIn("status", record)
        for name in ("nonce", "phrase", "PENDING", "OBSOLETE"):
            self.assertNotIn(name, json.dumps(self.content))

    def test_4d1_states_load_without_migration(self):
        state = CharacterState("aria", (concept(), concept(2, "dos")))
        content = encode_character_content(state)
        self.assertEqual((content["proposals"], content["proposal_decisions"]), ([], []))
        data = encode_state(content, revision=2)
        decoded = decode_character_state(content, forum_id="foro", revision=2)
        self.assertEqual(encode_state(encode_character_content(decoded), revision=2), data)
        self.assertEqual(decoded.replay.effective, concept_root("aria", concept(2, "dos")))

    def test_citations_need_the_resolver(self):
        with self.assertRaises(CharacterError):
            self.decode(self.content, resolver=None)
        with self.assertRaises(CharacterError):
            self.decode(self.content, resolver=lambda cid, v: (_ for _ in ()).throw(
                InstanceError("INVALID_STATE", "no vigente")))
        other = mock.Mock(return_value=mock.Mock(candidate_sha256="9" * 64))
        with self.assertRaises(CharacterError):
            self.decode(self.content, resolver=other)

    def test_every_tampering_is_rejected(self):
        changes = {
            "proposal text": lambda c: c["proposals"][0].update(text="otro"),
            "rationale": lambda c: c["proposals"][0].update(rationale="otro"),
            "proposal hash": lambda c: c["proposals"][0].update(proposal_sha256="0" * 64),
            "result hash": lambda c: c["proposals"][0].update(
                result_composition_sha256="0" * 64),
            "size": lambda c: c["proposals"][0].update(utf8_size=1),
            "created revision": lambda c: c["proposals"][1].update(created_revision=5),
            "base": lambda c: c["proposals"][0].update(base_composition_sha256="0" * 64),
            "concept ref": lambda c: c["proposals"][0]["concept"].update(version=2),
            "citation hash": lambda c: c["proposals"][0]["citations"][0].update(
                candidate_sha256="3" * 64),
            "citation extra key": lambda c: c["proposals"][0]["citations"][0].update(x=1),
            "citation order": lambda c: c["proposals"][0]["citations"].reverse(),
            "extra proposal key": lambda c: c["proposals"][0].update(status="PENDING"),
            "decision status": lambda c: c["proposal_decisions"][0].update(
                review_status="REJECTED"),
            "decision revision": lambda c: c["proposal_decisions"][0].update(decision_revision=3),
            "decision evidence": lambda c: c["proposal_decisions"][0]["evidence"].update(
                sha256="0" * 64),
            "decision locator": lambda c: c["proposal_decisions"][0]["evidence"].update(
                locator="x://y"),
            "decision receipt": lambda c: c["proposal_decisions"][0]["receipt"].update(
                method="OTRO"),
            "decision id": lambda c: c["proposal_decisions"][0].update(decision_id="x"),
            "decision of unknown proposal": lambda c: c["proposal_decisions"][0].update(
                proposal_id="zzz"),
            "decision with list id": lambda c: c["proposal_decisions"][0].update(
                proposal_id=["a"]),
            "removed decision": lambda c: c["proposal_decisions"].clear(),
            "proposals not a list": lambda c: c.update(proposals={}),
        }
        for name, change in changes.items():
            with self.subTest(name):
                content = copy.deepcopy(self.content)
                change(content)
                with self.assertRaises(CharacterError):
                    self.decode(content)

    def test_revision_must_match_the_event_log(self):
        for revision in (3, 5, 0, True):
            with self.subTest(revision=revision):
                with self.assertRaises(CharacterError):
                    self.decode(self.content, revision=revision)


class ProposalCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._base = Path(tempfile.mkdtemp())
        cls._workspace = closed_workspace(cls._base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._base)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        workspace = self.root / "ws"
        shutil.copytree(self._workspace, workspace)
        self.instance = self.root / "instancia"
        create_instance(workspace, output=self.instance, core_root=ROOT)
        self.import_concept(1, "# Aria\nExploradora curiosa.\n")

    def import_concept(self, version, text):
        path = self.root / f"concepto-{version}.md"
        path.write_bytes(text.encode("utf-8"))
        import_concept(self.instance, expected_core_root=ROOT, character_id="aria",
                       version=version, input_path=path, terminal=FakeTerminal())

    def loaded(self):
        return load_instance(self.instance, expected_core_root=ROOT)

    def effective(self):
        return get_effective_composition(self.loaded(), character_id="aria")

    def value(self, proposal_id="ajuste", version=1, base=None,
              text="# Aria\nExploradora valiente.\n", rationale="Encaja con normas v3.",
              citations=(("normas", 3),)):
        return {"proposal_id": proposal_id, "version": version,
                "base_composition_sha256": base or self.effective().composition_sha256,
                "text": text, "rationale": rationale,
                "citations": [{"candidate_id": c, "version": v} for c, v in citations]}

    def add(self, value=None, **kwargs):
        return add_proposal(self.instance, expected_core_root=ROOT, character_id="aria",
                            value=value if value is not None else self.value(**kwargs))

    def decide(self, proposal_id="ajuste", version=1, status=APPROVED, terminal=None):
        return record_proposal_decision(self.instance, expected_core_root=ROOT,
                                        character_id="aria", proposal_id=proposal_id,
                                        version=version, review_status=status,
                                        terminal=terminal or FakeTerminal())

    def view(self, proposal_id="ajuste", version=1):
        return get_proposal(self.loaded(), character_id="aria", proposal_id=proposal_id,
                            version=version)

    def state_path(self):
        return self.instance / "characters" / "aria" / "state.json"

    def lock_path(self):
        return self.instance / "characters" / "aria" / "state.json.lock"


class AddTest(ProposalCase):
    def test_add_persists_exact_record_and_changes_nothing_else(self):
        before = self.effective()
        result = self.add(citations=(("normas", 3), ("duda", 1)))
        self.assertTrue(result.created)
        self.assertEqual(result.character.state_revision, 2)
        instance = self.loaded()
        corpus = {e.candidate.key: e.candidate.candidate_sha256
                  for e in approved_corpus(instance)}
        _, content = load_state(self.state_path())
        record = content["proposals"][0]
        self.assertEqual(record["citations"], [
            {"candidate_id": "normas", "candidate_sha256": corpus[("normas", 3)], "version": 3},
            {"candidate_id": "duda", "candidate_sha256": corpus[("duda", 1)], "version": 1}])
        self.assertEqual(record["created_revision"], 2)
        self.assertEqual(record["concept"], before.concept.as_json())
        self.assertEqual(content["proposal_decisions"], [])
        self.assertEqual(self.effective(), before)
        view = self.view()
        self.assertEqual((view.status, view.decision, view.applied_to_effective),
                         (ProposalStatus.PENDING, None, False))
        self.assertFalse(self.lock_path().exists())

    def test_retry_is_idempotent_without_writing(self):
        self.add()
        data = self.state_path().read_bytes()
        mtime = os.stat(self.state_path()).st_mtime_ns
        with mock.patch.object(character_module, "_corpus_lock") as lock:
            result = self.add(base=self.view().proposal.base_composition_sha256)
        lock.assert_not_called()
        self.assertFalse(result.created)
        self.assertEqual(self.state_path().read_bytes(), data)
        self.assertEqual(os.stat(self.state_path()).st_mtime_ns, mtime)

    def test_conflicts(self):
        self.add()
        base = self.view().proposal.base_composition_sha256
        cases = {
            "same key other text": dict(base=base, text="Otro\n"),
            "same key other citations": dict(base=base, citations=(("mundo", 1),)),
            "version skip": dict(version=3),
            "repeats previous": dict(version=2),
            "stale base": dict(proposal_id="otra", base="0" * 64),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.add(**kwargs)
                self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(len(list_proposals(self.loaded(), character_id="aria")), 1)

    def test_input_rules(self):
        good = self.value()
        cases = {
            "not an object": [],
            "extra key": {**good, "status": "PENDING"},
            "candidate hash given": {**good, "citations": [{"candidate_id": "normas",
                                                            "version": 3,
                                                            "candidate_sha256": "1" * 64}]},
            "missing key": {k: v for k, v in good.items() if k != "rationale"},
            "bool version": {**good, "version": True},
            "string version": {**good, "version": "1"},
            "empty citations": {**good, "citations": []},
            "duplicate citation": {**good, "citations": [{"candidate_id": "normas",
                                                          "version": 3}] * 2},
            "bom text": {**good, "text": "\ufeffhola"},
            "control text": {**good, "text": "hola\x07"},
            "blank rationale": {**good, "rationale": "  "},
            "bad id": {**good, "proposal_id": "Ajuste"},
            "bad base": {**good, "base_composition_sha256": "XYZ"},
        }
        for name, value in cases.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.add(value)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertFalse(list_proposals(self.loaded(), character_id="aria"))

    def test_only_current_approved_candidates_can_be_cited(self):
        for name, cited in {"pending superseded": ("fichas", 2), "rejected": ("idea", 1),
                            "superseded approved": ("normas", 1), "missing": ("nada", 1),
                            "wrong version": ("mundo", 2)}.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.add(citations=(cited,))
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertTrue(self.add(citations=(("duda", 1),)).created)

    def test_several_pending_and_unknown_character(self):
        self.add(proposal_id="a")
        self.add(proposal_id="b", text="Otra alternativa\n")
        self.add(proposal_id="a", version=2, text="A revisada\n")
        statuses = [(v.proposal.key, v.status) for v in
                    list_proposals(self.loaded(), character_id="aria")]
        self.assertEqual(statuses, [(("a", 1), ProposalStatus.OBSOLETE),
                                    (("b", 1), ProposalStatus.PENDING),
                                    (("a", 2), ProposalStatus.PENDING)])
        with self.assertRaises(CharacterError) as ctx:
            add_proposal(self.instance, expected_core_root=ROOT, character_id="nadie",
                         value=self.value())
        self.assertEqual(ctx.exception.code, "INVALID_STATE")

    def test_concurrent_add_is_not_lost(self):
        real_lock = character_module._corpus_lock

        competitor = []

        def racing_lock(state_path, subject, guard=None):
            if not competitor:
                competitor.append(True)
                self.add(proposal_id="otra", text="Del otro proceso\n")
            return real_lock(state_path, subject, guard=guard)

        with mock.patch.object(character_module, "_corpus_lock", racing_lock):
            with self.assertRaises(CharacterError) as ctx:
                self.add()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual([v.proposal.proposal_id for v in
                          list_proposals(self.loaded(), character_id="aria")], ["otra"])

    def test_forged_citation_of_a_rejected_candidate_fails_to_load(self):
        instance = self.loaded()
        rejected = next(c for c in instance.candidates if c.key == ("idea", 1))
        state = instance.characters[0].state
        effective = state.replay.effective
        forged = CharacterProposal("aria", "falsa", 1, 2, effective.concept,
                                   effective.composition_sha256, "Texto\n", "Motivo",
                                   (CorpusCandidateRef("idea", 1, rejected.candidate_sha256),))
        content = encode_character_content(dataclasses.replace(state, proposals=(forged,)))
        self.state_path().write_bytes(encode_state(content, revision=2))
        with self.assertRaises(InstanceError):
            self.loaded()


class DecisionTest(ProposalCase):
    def expected_prompt(self, view, verb, current="SÍ"):
        p = view.proposal
        normas = next(c for c in self.loaded().candidates if c.key == ("normas", 3))
        base_text = view.base.text if view.base.text.endswith("\n") else view.base.text + "\n"
        text = p.text if p.text.endswith("\n") else p.text + "\n"
        return (
            "DECISIÓN HUMANA SOBRE PROPUESTA\n"
            "Personaje: aria\n"
            f"Propuesta: {p.proposal_id} v{p.version}\n"
            f"Estado antes de decidir: {view.status.value}\n"
            f"Decisión: {verb}\n"
            f"Concepto humano citado: v{p.concept.version}\n"
            f"Concepto SHA-256: {p.concept.concept_sha256}\n"
            f"Base vigente ahora: {current}\n"
            f"Base composición SHA-256: {p.base_composition_sha256}\n"
            f"Resultado composición SHA-256: {p.result_composition_sha256}\n"
            f"Propuesta SHA-256: {p.proposal_sha256}\n"
            f"Base bytes UTF-8: {view.base.utf8_size}\n"
            f"Propuesta bytes UTF-8: {p.utf8_size}\n"
            "Citas aprobadas (1):\n"
            f"Cita 1: normas v3 | LITERAL | RULES | APPROVED | sha256={normas.candidate_sha256}\n"
            "Motivo exacto (hasta «Fin del motivo.»):\n"
            f"{p.rationale}\n"
            "Fin del motivo.\n"
            "BASE CITADA — texto exacto (hasta «Fin de la base.»):\n"
            f"{base_text}"
            "Fin de la base.\n"
            "PROPUESTA — texto completo que se aprueba/rechaza (hasta «Fin de la propuesta.»):\n"
            f"{text}"
            "Fin de la propuesta.\n"
            + NOTICE)

    def test_approval_prompt_state_and_obsolescence(self):
        long_text = "".join(f"Línea {i}: «ñ» 🌊\r\n" for i in range(300)) + "sin salto final"
        self.add(text=long_text)
        self.add(proposal_id="otra", text="Alternativa\n")
        view = self.view()
        terminal = FakeTerminal()
        result = self.decide(terminal=terminal)
        prompt, phrase_line = terminal.output.rsplit("Escribe exactamente: ", 1)
        self.assertEqual(prompt, self.expected_prompt(view, "APROBAR"))
        self.assertRegex(phrase_line, r"^APROBAR-PROPUESTA ajuste v1 [A-HJ-NP-Z2-9]{8}\n> $")
        self.assertTrue(result.created)
        self.assertEqual(result.character.state_revision, 4)
        self.assertEqual((result.effective.text, result.effective.composition_sha256),
                         (long_text, view.proposal.result_composition_sha256))
        phrase = phrase_line[:-3]
        self.assertEqual(result.decision.receipt.confirmation_sha256,
                         hashlib.sha256(phrase.encode()).hexdigest())
        self.assertEqual(self.view("otra").status, ProposalStatus.OBSOLETE)
        approved = self.view()
        self.assertEqual((approved.status, approved.applied_to_effective),
                         (ProposalStatus.APPROVED, True))
        _, content = load_state(self.state_path())
        self.assertEqual(content["proposal_decisions"], [decision_record(result.decision)])
        self.assertEqual(content["proposal_decisions"][0]["decision_revision"], 4)
        self.assertEqual(len(content["proposals"]), 2)

    def test_retry_and_opposite_decision(self):
        self.add()
        self.decide()
        data = self.state_path().read_bytes()
        terminal = FakeTerminal()
        again = self.decide(terminal=terminal)
        self.assertEqual((again.created, terminal.output), (False, ""))
        self.assertEqual(self.state_path().read_bytes(), data)
        with self.assertRaises(CharacterError) as ctx:
            self.decide(status=REJECTED)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        for status in (ReviewStatus.PENDING_HUMAN_REVIEW, "APPROVED"):
            with self.assertRaises(CharacterError):
                self.decide(status=status)

    def test_reject_pending_and_obsolete(self):
        self.add(proposal_id="a")
        self.add(proposal_id="b", text="Otra\n")
        before = self.effective()
        self.decide("b", status=REJECTED)
        self.assertEqual(self.effective(), before)
        self.assertEqual(self.view("a").status, ProposalStatus.PENDING)
        self.decide("a")
        self.add(proposal_id="c", text="Tercera\n")
        self.add(proposal_id="c", version=2, text="Tercera bis\n")
        obsolete = self.view("c")
        self.assertEqual(obsolete.status, ProposalStatus.OBSOLETE)
        with self.assertRaises(CharacterError) as ctx:
            self.decide("c")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        terminal = FakeTerminal()
        after_a = self.effective()
        self.decide("c", status=REJECTED, terminal=terminal)
        self.assertIn("Estado antes de decidir: OBSOLETE\n", terminal.output)
        self.assertIn("Decisión: RECHAZAR\n", terminal.output)
        self.assertIn("Escribe exactamente: RECHAZAR-PROPUESTA c v1 ", terminal.output)
        self.assertEqual(self.effective(), after_a)
        self.assertEqual(self.view("c", 2).status, ProposalStatus.PENDING)

    def test_reject_shows_a_base_that_is_no_longer_current(self):
        self.add(proposal_id="a")
        self.add(proposal_id="b", text="Otra\n")
        self.decide("a")
        view = self.view("b")
        terminal = FakeTerminal()
        self.decide("b", status=REJECTED, terminal=terminal)
        self.assertEqual(terminal.output.rsplit("Escribe exactamente: ", 1)[0],
                         self.expected_prompt(view, "RECHAZAR", "NO"))

    def test_chain_and_concept_reset(self):
        self.add(proposal_id="a", text="Paso A\n")
        self.decide("a")
        self.add(proposal_id="b", text="Paso B\n")
        self.decide("b")
        self.add(proposal_id="c", text="Pendiente\n")
        effective = self.effective()
        self.assertEqual(([s.proposal.proposal_id for s in effective.applied_proposals],
                          effective.text), (["a", "b"], "Paso B\n"))
        self.import_concept(2, "# Aria\nConcepto nuevo.\n")
        reset = self.effective()
        self.assertEqual((reset.text, reset.applied_proposals, reset.concept.version),
                         ("# Aria\nConcepto nuevo.\n", (), 2))
        views = list_proposals(self.loaded(), character_id="aria")
        self.assertEqual([(v.proposal.proposal_id, v.status, v.applied_to_effective)
                          for v in views],
                         [("a", ProposalStatus.APPROVED, False),
                          ("b", ProposalStatus.APPROVED, False),
                          ("c", ProposalStatus.OBSOLETE, False)])
        self.assertEqual(self.loaded().characters[0].state_revision, 7)
        with self.assertRaises(CharacterError):
            self.decide("c")
        self.add(proposal_id="c", version=2, text="Pendiente\n")
        self.assertEqual(self.view("c", 2).proposal.concept.version, 2)

    def test_answer_rules_write_nothing(self):
        self.add()
        data = self.state_path().read_bytes()
        answers = {"lowercase": lambda p: p.lower() + "\n", "extra space": lambda p: p + " \n",
                   "leading space": lambda p: " " + p + "\n", "eof": lambda p: None,
                   "other phrase": lambda p: p.replace("APROBAR", "RECHAZAR") + "\n"}
        for name, transform in answers.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.decide(terminal=FakeTerminal(transform=transform))
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        terminal = FakeTerminal(interactive=False)
        with self.assertRaises(CharacterError):
            self.decide(terminal=terminal)
        self.assertEqual(terminal.output, "")

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.decide(terminal=FakeTerminal(on_read=interrupt))
        self.assertEqual(self.state_path().read_bytes(), data)
        self.assertFalse(self.lock_path().exists())

    def test_unknown_targets(self):
        self.add()
        for kwargs in (dict(proposal_id="nada"), dict(version=2), dict(proposal_id="Mal")):
            with self.subTest(kwargs=kwargs):
                terminal = FakeTerminal()
                with self.assertRaises(CharacterError) as ctx:
                    self.decide(terminal=terminal, **kwargs)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                self.assertEqual(terminal.output, "")

    def test_change_during_the_prompt_is_a_conflict(self):
        self.add()

        def concurrent():
            self.add(proposal_id="otra", text="Concurrente\n")

        with self.assertRaises(CharacterError) as ctx:
            self.decide(terminal=FakeTerminal(on_read=concurrent))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.view().status, ProposalStatus.PENDING)
        self.assertEqual(self.view("otra").status, ProposalStatus.PENDING)

    def test_locks_release_failure_and_failed_replace(self):
        self.add()
        self.lock_path().write_bytes(b"")
        terminal = FakeTerminal()
        with self.assertRaises(CharacterError) as ctx:
            self.decide(terminal=terminal)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(terminal.output, "")
        with self.assertRaises(CharacterError) as ctx:
            self.add(proposal_id="otra")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.lock_path().unlink()

        from core.runtime import persistence
        before = self.state_path().read_bytes()
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(CharacterError) as ctx:
                self.decide()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertEqual(self.state_path().read_bytes(), before)
        self.assertFalse(self.lock_path().exists())

        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            with self.assertRaises(CharacterError) as ctx:
                self.decide()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        self.lock_path().unlink()
        self.assertEqual(self.view().status, ProposalStatus.APPROVED)

    def swap_for_junction(self):
        import _winapi
        folder = self.instance / "characters" / "aria"
        aside = self.root / "fuera-aria"
        folder.rename(aside)
        _winapi.CreateJunction(str(aside), str(folder))
        return aside

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_when_taking_the_lock_writes_nothing_outside(self):
        self.add()
        real_lock = character_module._corpus_lock
        for action in (lambda: self.decide(), lambda: self.add(proposal_id="otra")):
            with self.subTest(action=action):
                swapped = {}

                def racing_lock(state_path, subject, guard=None):
                    swapped["aside"] = self.swap_for_junction()
                    return real_lock(state_path, subject, guard=guard)

                with mock.patch.object(character_module, "_corpus_lock", racing_lock):
                    with self.assertRaises(CharacterError) as ctx:
                        action()
                self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
                aside = swapped["aside"]
                self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
                self.assertEqual(load_state(aside / "state.json")[0], 2)
                os.rmdir(self.instance / "characters" / "aria")
                aside.rename(self.instance / "characters" / "aria")

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_right_before_writing_writes_nothing_outside(self):
        self.add()
        real_encode = character_module.encode_state
        swapped = {}

        def racing_encode(content, *, revision):
            data = real_encode(content, revision=revision)
            swapped["aside"] = self.swap_for_junction()
            return data

        with mock.patch.object(character_module, "encode_state", racing_encode):
            with self.assertRaises(CharacterError) as ctx:
                self.decide()
        self.assertIn(ctx.exception.code, ("UNSAFE_DESTINATION", "CONFLICT"))
        aside = swapped["aside"]
        self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
        self.assertEqual(load_state(aside / "state.json")[0], 2)


if __name__ == "__main__":
    unittest.main()
