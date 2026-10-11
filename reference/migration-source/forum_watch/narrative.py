"""One manual evaluation, durable jobs and review-only output; no reader calls."""

from uuid import uuid4

from . import drafts
from .context import build_context
from .models import WatchError, digest, json_text, require
from .policy import preflight
from .result import validate_result
from .store import now


def unfinished(store, link):
    return [dict(r) for r in store.conn.execute("""SELECT p.* FROM pending_changes p
        LEFT JOIN evaluation_jobs j ON j.change_id=p.id
        WHERE p.host=? AND p.topic_id=? AND j.change_id IS NULL
        ORDER BY p.capture_pk,p.ordinal,p.id""", (link.host, link.topic_id))]


def complete(store, run_id, decision, reason, result=None):
    store.conn.execute("UPDATE evaluation_runs SET decision=?,reason=?,completed_at=?,result_json=? WHERE run_id=?",
                       (decision, reason, now(), json_text(result) if result else None, run_id))
    store.conn.execute("UPDATE evaluation_jobs SET decision=? WHERE run_id=?", (decision, run_id))


def evaluate(store, url, model=None):
    require(store.settings.expected_account_id == 59, "NARRATIVE_ACCOUNT_MISMATCH", "The existing Nozomu interpreter is bound to account 59.")
    drafts.initialize(store)
    link = store._link(url)
    with drafts.evaluation_lock(store):
        with store.transaction():
            # Exclusive OS lock proves an old RUNNING run is no longer executing.
            # After a crash it fails, rather than invoking the model twice.
            for row in store.conn.execute("SELECT run_id FROM evaluation_runs WHERE decision='RUNNING'").fetchall():
                complete(store, row[0], "GENERATION_FAILED", "INTERRUPTED_EXECUTION: preserved claim; no automatic retry.")
            drafts.observe_manual_edits(store, link)
            drafts.invalidate(store, link)
            changes = unfinished(store, link)
            claimed_dependencies = drafts.dependencies(store, link)
            revisions = {r["message_id"]: r["revision"] for r in claimed_dependencies}
            decision = preflight(store._topic(link), changes, revisions, drafts.pending_draft(store, link))
            if not changes:
                return {"decision": decision[0], "reason": decision[1], "model_called": False,
                        "jobs_evaluated": 0, "tracking_state": store._topic(link)["state"]}
            run_id = uuid4().hex
            store.conn.execute("""INSERT INTO evaluation_runs
                (run_id,host,topic_id,created_at,decision,reason,model_called)
                VALUES(?,?,?,?,'RUNNING','Manual evaluation',0)""", (run_id, link.host, link.topic_id, now()))
            store.conn.executemany("INSERT INTO evaluation_jobs VALUES(?,?,'RUNNING')", [(c["id"], run_id) for c in changes])
            if decision:
                complete(store, run_id, *decision)
                return {"run_id": run_id, "decision": decision[0], "reason": decision[1], "model_called": False,
                        "jobs_evaluated": len(changes)}
        called = False
        artifact = None
        try:
            package = build_context(store, link, changes)
            used = [{"message_id": m["message_id"], "revision": m["revision"]} for m in package["SCENE"]["messages"]]
            require(used == claimed_dependencies, "CONTEXT_CHANGED_BEFORE_GENERATION", "The claimed context changed before generation.")
            with store.transaction():
                store.conn.execute("UPDATE evaluation_runs SET context_hash=?,context_json=?,source_versions_json=? WHERE run_id=?",
                                   (digest(json_text(package)), json_text(package), json_text(package["source_versions"]), run_id))
            if model is None:
                from .codex_runner import CodexInterpreter
                model = CodexInterpreter()
            with store.transaction():
                store.conn.execute("UPDATE evaluation_runs SET model_called=1 WHERE run_id=?", (run_id,))
            called = True
            result = validate_result(model.generate(package), package)
            if getattr(model, "last_evidence", None):
                result["runtime_evidence"] = model.last_evidence
            with store.transaction():
                drafts.observe_manual_edits(store, link)
                if drafts.dependencies(store, link) != used or store._topic(link)["state"] == "CLOSED":
                    complete(store, run_id, "NEEDS_HUMAN_REVIEW", "Context changed during generation; output retained as data only.", result)
                    return {"run_id": run_id, "decision": "NEEDS_HUMAN_REVIEW", "model_called": True, "jobs_evaluated": len(changes)}
                if result["decision"] == "DRAFT_READY":
                    require(not drafts.pending_draft(store, link), "DRAFT_CONFLICT", "A pending draft appeared during generation.")
                    artifact = drafts.persist(store, link, run_id, package, result["draft"])
                if result["decision"] == "COMBAT_REVIEW_REQUIRED":
                    # A handoff is data for the EXISTING specialist. No automatic
                    # spawning, attack resolution, inventory change or publication.
                    result["combat_handoff"] = {"target": "nozomu_combat", "context_hash": digest(json_text(package)),
                                                "messages": package["SCENE"]["messages"],
                                                "assessment": result["scene_assessment"],
                                                "scene_resources": "UNKNOWN; consult confirmed profile and scene sources",
                                                "status": "PENDING_SPECIALIST_AND_HUMAN_REVIEW"}
                complete(store, run_id, result["decision"], result["reason"], result)
            return {"run_id": run_id, "decision": result["decision"], "reason": result["reason"],
                    "model_called": True, "jobs_evaluated": len(changes), "draft": artifact}
        except (Exception, KeyboardInterrupt) as exc:
            called = getattr(model, "invocation_started", called)
            code = exc.code if isinstance(exc, WatchError) else type(exc).__name__
            if artifact:
                drafts.cleanup_uncommitted(store, artifact)
            decision = "NEEDS_HUMAN_REVIEW" if code in {"CONTEXT_TOO_LARGE", "CONTEXT_CHANGED_BEFORE_GENERATION"} else "GENERATION_FAILED"
            with store.transaction():
                store.conn.execute("UPDATE evaluation_runs SET model_called=? WHERE run_id=?", (int(called), run_id))
                complete(store, run_id, decision, "Generation rejected: " + code)
            return {"run_id": run_id, "decision": decision, "error": code,
                    "model_called": called, "jobs_evaluated": len(changes)}


def evaluations(store, url):
    drafts.initialize(store)
    link = store._link(url)
    return [dict(r) for r in store.conn.execute("""SELECT run_id,created_at,completed_at,decision,reason,model_called,
        context_hash,source_versions_json,result_json FROM evaluation_runs WHERE host=? AND topic_id=? ORDER BY created_at""",
                                               (link.host, link.topic_id))]
