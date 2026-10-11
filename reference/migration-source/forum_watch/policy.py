"""Only demonstrable pre-model filters; no keyword-based roleplay decisions."""

DECISIONS = {"NO_RESPONSE_NEEDED", "WAIT_FOR_TURN", "NEEDS_HUMAN_REVIEW",
             "COMBAT_REVIEW_REQUIRED", "DRAFT_READY", "GENERATION_FAILED"}


def preflight(topic, changes, current_revisions, has_pending_draft):
    if not changes:
        return "NO_RESPONSE_NEEDED", "No hay versiones nuevas pendientes de evaluación."
    if topic["state"] == "CLOSED":
        return "NO_RESPONSE_NEEDED", "El tema está cerrado."
    if changes[-1]["is_own"]:
        return "NO_RESPONSE_NEEDED", "El último cambio pendiente pertenece a la cuenta propia."
    if all(current_revisions.get(c["message_id"]) != c["revision"] for c in changes):
        return "NO_RESPONSE_NEEDED", "Las versiones pendientes ya fueron sustituidas."
    if has_pending_draft:
        return "NEEDS_HUMAN_REVIEW", "Hay un borrador pendiente, activo o STALE; revisarlo y retirarlo explícitamente antes de generar otro."
    return None
