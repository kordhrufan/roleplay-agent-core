import copy
import dataclasses
import hashlib
import unittest

from core.character.models import (
    CharacterError,
    CharacterState,
    ConceptAuthorship,
    ConceptVersion,
    concept_summary,
    decode_character_state,
    encode_character_content,
    make_concept_version,
)
from core.runtime.assimilation import HumanConfirmationReceipt
from core.runtime.persistence import canonical_json_bytes

RECEIPT = HumanConfirmationReceipt("TTY_NONCE_V1", "a" * 64)


def concept(version: int = 1, text: str = "Concepto\n", character_id: str = "aria",
            forum_id: str = "foro") -> ConceptVersion:
    return make_concept_version(forum_id=forum_id, character_id=character_id, version=version,
                                text=text, receipt=RECEIPT)


class ConceptVersionTest(unittest.TestCase):
    def test_hash_size_and_immutability(self):
        text = "Ñandú — 🧭\r\nsegunda línea\tcon tab"
        c = concept(text=text)
        data = text.encode("utf-8")
        self.assertEqual((c.concept_sha256, c.utf8_size), (hashlib.sha256(data).hexdigest(), len(data)))
        self.assertIs(c.authorship, ConceptAuthorship.HUMAN_DECLARED)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.text = "otro"

    def test_text_is_kept_exactly(self):
        for text in ("sin salto", "con LF\n", "con CRLF\r\n", "  espacios  \n\n"):
            with self.subTest(text=text):
                self.assertEqual(concept(text=text).text, text)

    def test_invalid_text(self):
        for text in ("", "   \n\t", "nul\x00", "bell\x07", "esc\x1b[0m", "\ufeffbom", "\ud800",
                     None, 3):
            with self.subTest(text=repr(text)):
                with self.assertRaises(CharacterError):
                    concept(text=text)

    def test_invalid_ids_and_versions(self):
        for character_id in ("Aria", "a_b", "-a", "", "a--b"):
            with self.subTest(character_id=character_id):
                with self.assertRaises(CharacterError):
                    concept(character_id=character_id)
        for version in (0, -1, True, "1"):
            with self.subTest(version=version):
                with self.assertRaises(CharacterError):
                    concept(version=version)

    def test_evidence(self):
        c = concept(version=2, character_id="aria", forum_id="mi-foro")
        self.assertEqual(c.evidence.source_id, "human-concept:aria:v2")
        self.assertEqual(c.evidence.locator, "instance://mi-foro/characters/aria/concepts/v2")
        self.assertEqual(c.evidence.section_or_passage, "concept:aria:v2")
        payload = {"authorship": "HUMAN_DECLARED", "character_id": "aria",
                   "concept_sha256": c.concept_sha256,
                   "receipt": {"confirmation_sha256": "a" * 64, "method": "TTY_NONCE_V1"},
                   "text": c.text, "utf8_size": c.utf8_size, "version": 2}
        self.assertEqual(c.evidence.sha256,
                         hashlib.sha256(canonical_json_bytes(payload, pretty=False)).hexdigest())
        self.assertIsNone(c.evidence.observed_at)

    def test_requires_receipt_and_evidence(self):
        c = concept()
        with self.assertRaises(CharacterError):
            ConceptVersion(1, "x", ConceptAuthorship.HUMAN_DECLARED, None, c.evidence)
        with self.assertRaises(CharacterError):
            ConceptVersion(1, "x", ConceptAuthorship.HUMAN_DECLARED, RECEIPT, None)

    def test_summary(self):
        c = concept()
        self.assertEqual(concept_summary(c), {"authorship": "HUMAN_DECLARED",
                                              "concept_sha256": c.concept_sha256,
                                              "evidence_sha256": c.evidence.sha256,
                                              "utf8_size": c.utf8_size, "version": 1})


class CharacterStateTest(unittest.TestCase):
    def test_contiguous_versions_and_current(self):
        state = CharacterState("aria", (concept(1, "uno"), concept(2, "dos")))
        self.assertEqual(state.current_concept().text, "dos")
        for concepts in ((), (concept(2, "dos"),), (concept(1, "uno"), concept(3, "tres")),
                         (concept(1, "uno"), concept(2, "uno"))):
            with self.subTest(versions=[c.version for c in concepts]):
                with self.assertRaises(CharacterError):
                    CharacterState("aria", concepts)

    def test_histories_must_hold_their_models(self):
        with self.assertRaises(CharacterError):
            CharacterState("aria", (concept(),), proposals=("x",))
        with self.assertRaises(CharacterError):
            CharacterState("aria", (concept(),), proposal_decisions=("x",))


class CodecTest(unittest.TestCase):
    def setUp(self):
        self.state = CharacterState("aria", (concept(1, "uno\r\n"), concept(2, "dos")))
        self.content = encode_character_content(self.state)

    def test_round_trip_and_shape(self):
        self.assertEqual(set(self.content), {"character_id", "concepts", "proposal_decisions",
                                             "proposals"})
        self.assertEqual(set(self.content["concepts"][0]),
                         {"authorship", "concept_sha256", "evidence", "receipt", "text",
                          "utf8_size", "version"})
        self.assertEqual(decode_character_state(self.content, forum_id="foro", revision=2),
                         self.state)

    def test_decode_rejects_tampering(self):
        changes = {
            "text": lambda c: c["concepts"][0].update(text="otro"),
            "hash": lambda c: c["concepts"][0].update(concept_sha256="0" * 64),
            "size": lambda c: c["concepts"][0].update(utf8_size=1),
            "evidence": lambda c: c["concepts"][0]["evidence"].update(sha256="0" * 64),
            "locator": lambda c: c["concepts"][0]["evidence"].update(locator="x://y"),
            "receipt": lambda c: c["concepts"][0]["receipt"].update(method="OTRO"),
            "authorship": lambda c: c["concepts"][0].update(authorship="AGENT"),
            "extra key": lambda c: c["concepts"][0].update(nota="x"),
            "root key": lambda c: c.update(extra=1),
            "proposals": lambda c: c.update(proposals=[{}]),
            "order": lambda c: c["concepts"].reverse(),
            "id": lambda c: c.update(character_id="otro"),
        }
        for name, change in changes.items():
            with self.subTest(name):
                content = copy.deepcopy(self.content)
                change(content)
                with self.assertRaises(CharacterError):
                    decode_character_state(content, forum_id="foro", revision=2)

    def test_decode_checks_forum_and_revision(self):
        with self.assertRaises(CharacterError):
            decode_character_state(self.content, forum_id="otro-foro", revision=2)
        for revision in (0, -1, True, 1, 3):
            with self.subTest(revision=revision):
                with self.assertRaises(CharacterError):
                    decode_character_state(self.content, forum_id="foro", revision=revision)


if __name__ == "__main__":
    unittest.main()
