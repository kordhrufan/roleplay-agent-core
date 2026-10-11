"""Manual adapter: material the user provides by hand.

For now it only imports a forum dossier written by the user. Reading forum turns arrives in a
later increment; this adapter never publishes.
"""

from __future__ import annotations

from pathlib import Path

from core.runtime.assimilation import (
    _HEADINGS,
    DossierAssessment,
    DossierError,
    LoadedForumDossier,
    assess_dossier,
    load_dossier,
)


class ManualAdapterError(ValueError):
    """The dossier cannot be imported. `assessment` is set when required sections are missing."""

    def __init__(self, reason: str, assessment: DossierAssessment | None = None):
        self.reason = reason
        self.assessment = assessment
        super().__init__(reason)


def load_manual_dossier(dossier_dir: Path) -> LoadedForumDossier:
    """Load a user dossier and require every required section to be provided."""
    try:
        loaded = load_dossier(dossier_dir)
    except DossierError as exc:
        raise ManualAdapterError(str(exc)) from exc
    assessment = assess_dossier(loaded.dossier)
    if not assessment.ready_for_assimilation:
        missing = ", ".join(f"«{_HEADINGS[s]}»" for s in assessment.missing_required)
        raise ManualAdapterError(
            f"el expediente no está listo: faltan secciones obligatorias ({missing}); "
            "añade sus fuentes antes de importarlo",
            assessment,
        )
    return loaded
