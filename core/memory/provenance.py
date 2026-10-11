"""Source references attached to every persisted claim."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a claim comes from.

    `observed_at` is when the source was imported or observed; `ic_date` is the in-character
    date stated by the source. They are independent and never derived from each other.
    `sha256` accepts either case and is stored lowercase, so equal hashes compare equal.
    """

    source_id: str
    locator: str
    sha256: str | None = None
    section_or_passage: str | None = None
    observed_at: datetime | None = None
    ic_date: str | None = None

    def __post_init__(self) -> None:
        _require_text("source_id", self.source_id)
        _require_text("locator", self.locator)
        for name in ("section_or_passage", "ic_date"):
            value = getattr(self, name)
            if value is not None:
                _require_text(name, value)
        if self.sha256 is not None and not (
            isinstance(self.sha256, str) and _SHA256.fullmatch(self.sha256)
        ):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        if self.sha256 is not None:
            object.__setattr__(self, "sha256", self.sha256.lower())
        if self.observed_at is not None and (
            not isinstance(self.observed_at, datetime) or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime")
