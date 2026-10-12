"""Builds closed assimilation workspaces for the instance tests."""

import shutil
from pathlib import Path

from adapters.manual import load_manual_dossier
from core.review.models import ReviewStatus
from core.runtime.assimilation import add_candidate, close_assimilation, record_candidate_decision
from core.runtime.workspace import CORPUS_STATE, create_workspace, load_workspace
from tests.test_assimilation_decisions import LITERALS, FakeTerminal, literal_input

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"


def add(workspace: Path, value: dict) -> None:
    loaded = load_workspace(workspace)
    add_candidate(workspace / CORPUS_STATE, dossier=loaded.dossier,
                  expected_revision=loaded.corpus_revision, value=value)


def decide(workspace: Path, candidate_id: str, version: int = 1,
           status: ReviewStatus = ReviewStatus.APPROVED) -> None:
    loaded = load_workspace(workspace)
    record_candidate_decision(workspace / CORPUS_STATE, dossier=loaded.dossier,
                              expected_revision=loaded.corpus_revision, candidate_id=candidate_id,
                              version=version, review_status=status, terminal=FakeTerminal())


def close(workspace: Path) -> None:
    loaded = load_workspace(workspace)
    close_assimilation(workspace / CORPUS_STATE, dossier=loaded.dossier,
                       expected_revision=loaded.corpus_revision, terminal=FakeTerminal())


def open_workspace(root: Path, name: str = "ws") -> Path:
    """A workspace with every literal pending, plus a rejected and a superseded history."""
    dossier = root / "exp"
    if not dossier.exists():
        shutil.copytree(FIXTURE, dossier)
    workspace = root / name
    create_workspace(load_manual_dossier(dossier), dossier_dir=dossier, workspace=workspace,
                     core_root=ROOT)
    for candidate_id in LITERALS:
        add(workspace, literal_input(candidate_id))
    return workspace


def closed_workspace(root: Path, name: str = "ws") -> Path:
    """Closed corpus with approved literals (normas v3, fichas v3...), a rejected proposal, an
    approved uncertainty, a superseded approved version (normas v1) and superseded pending ones
    (normas v2, fichas v1 and v2)."""
    workspace = open_workspace(root, name)
    decide(workspace, "normas")
    add(workspace, literal_input("normas", version=2, cls="INTERPRETATION",
                                 text="Respeto mutuo entre participantes."))
    add(workspace, literal_input("fichas", version=2, cls="INTERPRETATION",
                                 text="La ficha lista los datos básicos."))
    add(workspace, {"candidate_id": "idea", "version": 1, "domain": "RULES", "class": "PROPOSAL",
                    "text": "Proponer turnos semanales.", "scope": "foro",
                    "citations": [{"dossier_section": "forum_rules", "source_id": "manual-foro",
                                   "source_version": "1", "declared_passage": "Convivencia",
                                   "quote": "turno"}]})
    add(workspace, {"candidate_id": "duda", "version": 1, "domain": "WORLD", "class": "UNCERTAINTY",
                    "text": "No consta el clima.", "scope": "foro",
                    "citations": [{"dossier_section": "setting", "source_id": "mundo-base",
                                   "source_version": "2", "declared_passage": None,
                                   "quote": "- Costa norte"}]})
    add(workspace, literal_input("fichas", version=3))
    add(workspace, literal_input("normas", version=3))
    for candidate_id, version in (("normas", 3), ("mundo", 1), ("fichas", 3), ("staff", 1),
                                  ("formato", 1), ("duda", 1)):
        decide(workspace, candidate_id, version)
    decide(workspace, "idea", 1, ReviewStatus.REJECTED)
    close(workspace)
    return workspace
