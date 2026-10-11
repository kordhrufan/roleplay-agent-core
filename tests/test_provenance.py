import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from core.memory.provenance import SourceRef

HASH = "a" * 64


class SourceRefTest(unittest.TestCase):
    def test_minimal_reference_leaves_optional_fields_unknown(self):
        ref = SourceRef("turn-1", "topics/scene/sources/turn-1.txt")
        self.assertIsNone(ref.sha256)
        self.assertIsNone(ref.section_or_passage)
        self.assertIsNone(ref.observed_at)
        self.assertIsNone(ref.ic_date)

    def test_observed_and_ic_dates_stay_independent(self):
        observed = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
        only_observed = SourceRef("s", "loc", observed_at=observed)
        self.assertIsNone(only_observed.ic_date)
        only_ic = SourceRef("s", "loc", ic_date="Año 3, otoño")
        self.assertIsNone(only_ic.observed_at)
        both = SourceRef("s", "loc", observed_at=observed, ic_date="Año 3, otoño")
        self.assertEqual(both.observed_at, observed)
        self.assertEqual(both.ic_date, "Año 3, otoño")

    def test_observed_at_requires_timezone(self):
        with self.assertRaises(ValueError):
            SourceRef("s", "loc", observed_at=datetime(2026, 9, 11, 10, 0))
        SourceRef("s", "loc", observed_at=datetime(2026, 9, 11, tzinfo=timezone(timedelta(hours=2))))

    def test_observed_at_must_be_datetime(self):
        with self.assertRaises(ValueError):
            SourceRef("s", "loc", observed_at="2026-09-11T10:00:00Z")

    def test_required_fields_must_be_non_empty_text(self):
        for source_id, locator in (("", "loc"), ("  ", "loc"), ("s", ""), (None, "loc"), ("s", 3)):
            with self.subTest(source_id=source_id, locator=locator):
                with self.assertRaises(ValueError):
                    SourceRef(source_id, locator)

    def test_optional_text_fields_cannot_be_blank(self):
        for field in ("section_or_passage", "ic_date"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    SourceRef("s", "loc", **{field: " "})

    def test_sha256_accepts_legacy_uppercase_and_stores_lowercase(self):
        # Same format as the legacy events.jsonl (PowerShell Get-FileHash output).
        legacy = "FBFA44EF" + "0123456789ABCDEF" * 3 + "01234567"
        ref = SourceRef("s", "loc", sha256=legacy)
        self.assertEqual(ref.sha256, legacy.lower())
        self.assertEqual(ref, SourceRef("s", "loc", sha256=legacy.lower()))

    def test_sha256_must_be_64_hex(self):
        SourceRef("s", "loc", sha256=HASH)
        for bad in ("a" * 63, "a" * 65, "g" * 64, "", 64):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    SourceRef("s", "loc", sha256=bad)

    def test_is_immutable(self):
        ref = SourceRef("s", "loc")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.locator = "other"


if __name__ == "__main__":
    unittest.main()
