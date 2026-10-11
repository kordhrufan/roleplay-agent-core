"""One deterministic cycle. Only ACTIVE topics; independent durable component phases."""

from pathlib import Path
from uuid import uuid4

from . import drafts, notifications, workflow_state
from .models import WatchError, require
from .narrative import complete, evaluate
from .store import Store, WORKSPACE, now
from .workflow_audit import Audit, COUNTERS, cycle_lock, error_code
from .workflow_config import load, operational_root

LOGIN_ERRORS = {"SESSION_EXPIRED", "SESSION_UNVERIFIABLE"}
ACCESS_ERRORS = {"ACCESS_DENIED", "WRONG_ACCOUNT"}


def live_reader(store, topic, config):
    require(store.storage_mode == "AUTHENTICATED_ONLY" and topic["topic_id"] == 275,
            "UNAUTHORIZED_LIVE_WORKFLOW", "Live workflow is restricted to authenticated topic 275.")
    return store.read_once(config["browser_profile"], max_pages=config["max_pages"],
                           time_budget_seconds=config["read_timeout_seconds"])


def recover_generation(store):
    if not drafts.installed(store):
        return 0
    with drafts.evaluation_lock(store), store.transaction():
        rows = store.conn.execute("SELECT run_id FROM evaluation_runs WHERE decision='RUNNING'").fetchall()
        for row in rows:
            complete(store, row[0], "GENERATION_FAILED", "INTERRUPTED_EXECUTION: preserved claim; no automatic retry.")
        return len(rows)


def run_once(config_path=None, *, trigger="MANUAL", reader=None, model=None, transport=None,
             root=None, notification_control=None):
    require(trigger in {"MANUAL", "SCHEDULED"}, "INVALID_RUN_TRIGGER", "Use MANUAL or SCHEDULED.")
    root = Path(root).resolve() if root is not None else operational_root()
    require(not root.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Run state must be external.")
    run = {"run_id": uuid4().hex, "started_at": now(), "finished_at": None, "trigger": trigger,
           "status": "RUNNING", **{name: 0 for name in COUNTERS}, "error_summary": [], "topics": [],
           "phase": "LOCK", "config_hash": None}
    audit = Audit(root)
    try:
        with cycle_lock(root) as acquired:
            if not acquired:
                run.update(status="SKIPPED_LOCKED", finished_at=now())
                audit.save(run)
                return run
            audit.recover()
            audit.save(run)
            try:
                run["phase"] = "CONFIG"
                config = load(config_path)
                run["config_hash"] = config["config_hash"]
                with Store(config["database"], storage_mode=config["storage_mode"]) as store:
                    workflow_state.initialize(store)
                    run["phase"] = "RECOVERY"
                    recovered = recover_generation(store)
                    if recovered:
                        run["error_summary"].append({"phase": "RECOVERY", "code": "INTERRUPTED_GENERATION", "count": recovered})
                    topics = store.list_topics()
                    run["topics_considered"] = len(topics)
                    for topic in topics:
                        item = {"topic_id": topic["topic_id"], "state_before": topic["state"], "phase": "SELECT",
                                "status": "PENDING", "session_identity_status": "NOT_CHECKED"}
                        run["topics"].append(item)
                        if topic["state"] != "ACTIVE":
                            item.update(status="SKIPPED_" + topic["state"])
                            audit.save(run)
                            continue
                        link = store._link(topic["canonical_url"])
                        try:
                            # Recheck after each previous topic; a user's pause takes
                            # effect before the next live operation, not next cycle.
                            current = workflow_state.effective_topic(store, store._topic(link))
                            if current["state"] != "ACTIVE":
                                item.update(status="SKIPPED_" + current["state"])
                                audit.save(run)
                                continue
                            item["phase"] = run["phase"] = "READ"
                            observed = (reader or live_reader)(store, topic, config)
                            if store.storage_mode == "AUTHENTICATED_ONLY":
                                require(observed.get("session_identity_status") == "VERIFIED_FOR_THIS_EXECUTION"
                                        and observed.get("observed_account_id") == 59,
                                        "SESSION_UNVERIFIABLE", "Reader did not provide fresh account 59 evidence.")
                            run["topics_read"] += 1
                            run["changes_detected"] += observed.get("new_changes", 0) + observed.get("edit_changes", 0)
                            item.update(read_result=observed["result"], session_identity_status=observed.get("session_identity_status", "SYNTHETIC"),
                                        observed_account_id=observed.get("observed_account_id"),
                                        observed_at=observed.get("observed_at"), status=observed["result"])
                            audit.save(run)
                            current = workflow_state.effective_topic(store, store._topic(link))
                            if current["state"] != "ACTIVE":
                                item.update(status="SKIPPED_" + current["state"], model_called=False)
                                audit.save(run)
                                continue
                            item["phase"] = run["phase"] = "EVALUATE"
                            # A recovered unread job remains genuine work even if
                            # this fresh capture itself has no additional edits.
                            if store.pending(topic["canonical_url"]):
                                interpreter = model
                                if interpreter is None:
                                    from .codex_runner import CodexInterpreter
                                    interpreter = CodexInterpreter(timeout_seconds=config["generation_timeout_seconds"],
                                                                   binary=config["codex_executable"])
                                result = evaluate(store, topic["canonical_url"], interpreter)
                                run["jobs_evaluated"] += result["jobs_evaluated"]
                                run["drafts_created"] += int(bool(result.get("draft")))
                                item.update(evaluation=result["decision"], model_called=result["model_called"], status=result["decision"])
                                if result["decision"] == "GENERATION_FAILED":
                                    run["error_summary"].append({"phase": "EVALUATE", "topic_id": topic["topic_id"], "code": "GENERATION_FAILED"})
                            else:
                                item["model_called"] = False
                            audit.save(run)
                        except Exception as error:
                            code = error_code(error)
                            item.update(status="FAILED", error=code)
                            if code in LOGIN_ERRORS | ACCESS_ERRORS:
                                saved_id = getattr(error, "details", {}).get("recorded_error_id")
                                if saved_id is None:
                                    safe = WatchError(code, "Workflow access/session check failed; manual recovery required.")
                                    store._record_error(safe, link)
                                    saved_id = safe.details["recorded_error_id"]
                                workflow_state.block_topic(store, link, code, saved_id)
                                item["state_after"] = workflow_state.effective_topic(store, store._topic(link))["state"]
                            run["error_summary"].append({"phase": item["phase"], "topic_id": topic["topic_id"], "code": code})
                            audit.save(run)
                    run["phase"] = "NOTIFICATIONS"
                    run["notifications_created"] += notifications.collect(store)["queued"]
                    eligible = store.conn.execute("""SELECT count(*) FROM notifications
                        WHERE (status IN ('PENDING','FAILED_RETRYABLE') AND attempt_count<3)
                        OR status='SENDING'""").fetchone()[0]
                    if eligible:
                        delivery = notifications.send_pending(store, transport, limit=config["notification_limit"],
                                                              control=notification_control)
                        for result in delivery["notifications"]:
                            run["notifications_sent"] += int(result["status"] == "SENT")
                            if result["status"].startswith("FAILED"):
                                run["error_summary"].append({"phase": "NOTIFICATIONS", "code": result["last_error"]})
                    run["status"] = "COMPLETED" if not run["error_summary"] else "COMPLETED_WITH_ERRORS"
            except (Exception, KeyboardInterrupt) as error:
                run["status"] = "FAILED"
                run["error_summary"].append({"phase": run["phase"], "code": error_code(error)})
            run["finished_at"], run["phase"] = now(), "FINISHED"
            audit.save(run)
            return run
    finally:
        audit.close()


def status(config_path=None, *, root=None):
    config = load(config_path)
    root = Path(root) if root is not None else operational_root()
    with Store(config["database"], storage_mode=config["storage_mode"]) as store:
        topics = store.list_topics()
        events = store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='notifications'").fetchone()
        queue = dict(store.conn.execute("SELECT status,count(*) FROM notifications GROUP BY status")) if events else {}
        snapshots = []
        for topic in topics:
            inspected = store.inspect(topic["canonical_url"])
            snapshots.append({"topic_id": topic["topic_id"], "state": topic["state"],
                              "last_valid_capture": inspected["last_valid_capture"],
                              "session_identity_status": "NOT_VERIFIED_BY_STATUS_COMMAND",
                              "pending_count": inspected["pending_count"]})
    runs = []
    if (root / "workflow-runs.sqlite3").is_file():
        audit = Audit(root)
        try:
            runs = audit.latest()
        finally:
            audit.close()
    return {"interval_seconds": config["interval_seconds"], "topics": snapshots,
            "notifications": queue, "runs": runs, "publication": "NOT_IMPLEMENTED",
            "automatic_canonical_memory": False}
