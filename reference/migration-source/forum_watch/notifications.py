"""Manual outbox over committed records. No model, reader or secret access."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
from uuid import uuid4

from .models import json_text, load_json, require
from .store import WORKSPACE, now

NOTIFIABLE = {"DRAFT_READY", "NEEDS_HUMAN_REVIEW", "COMBAT_REVIEW_REQUIRED", "GENERATION_FAILED",
              "SESSION_EXPIRED", "ACCESS_DENIED", "STALE"}
MAX_ATTEMPTS = 3
READER_TYPES = {"SESSION_EXPIRED": "SESSION_EXPIRED", "ACCESS_DENIED": "ACCESS_DENIED",
                "WRONG_ACCOUNT": "ACCESS_DENIED", "SESSION_UNVERIFIABLE": "NEEDS_HUMAN_REVIEW",
                "HTTP_READ_FAILED": "NEEDS_HUMAN_REVIEW"}
CONNECTION_TEST = ("Nozumo Forum Watch — prueba de notificación.\n\n"
                   "La conexión con Discord funciona.\n"
                   "No se ha publicado ningún mensaje en Naruto Rol.")
LABELS = {
    "DRAFT_READY": ("Borrador preparado", "Pendiente de revisión"),
    "STALE": ("Borrador desactualizado", "Necesita una nueva revisión antes de utilizarlo"),
    "NEEDS_HUMAN_REVIEW": ("Revisión humana necesaria", "Pendiente de revisión humana"),
    "COMBAT_REVIEW_REQUIRED": ("Revisión de combate necesaria", "Pendiente del especialista y revisión humana"),
    "GENERATION_FAILED": ("No se pudo preparar el borrador", "Revisar el error operativo local"),
    "SESSION_EXPIRED": ("Inicio de sesión necesario", "La sesión del foro ya no es válida"),
    "ACCESS_DENIED": ("Acceso al foro denegado", "Revisar la sesión y la cuenta autorizada"),
}
DDL = (
    "CREATE TABLE notification_meta(version INTEGER NOT NULL CHECK(version=1), namespace TEXT NOT NULL)",
    """CREATE TABLE notifications (
        notification_id TEXT PRIMARY KEY, source_event_id TEXT NOT NULL UNIQUE,
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, type TEXT NOT NULL,
        created_at TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 3),
        last_attempt_at TEXT, status TEXT NOT NULL CHECK(status IN
            ('PENDING','SENDING','SENT','FAILED_RETRYABLE','FAILED_FINAL','SUPERSEDED')),
        remote_message_id TEXT, last_error TEXT, next_attempt_at REAL NOT NULL DEFAULT 0,
        delivery_uncertain INTEGER NOT NULL DEFAULT 0, event_json TEXT NOT NULL,
        FOREIGN KEY(host,topic_id) REFERENCES topics(host,topic_id))""",
    """CREATE TABLE notification_attempts(
        notification_id TEXT NOT NULL, attempt INTEGER NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, status TEXT NOT NULL, error TEXT,
        PRIMARY KEY(notification_id,attempt),
        FOREIGN KEY(notification_id) REFERENCES notifications(notification_id))""",
)


def initialize(store):
    require(not store.path.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH",
            "Notification state must stay outside the character tree.")
    with store.transaction():
        if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='notification_meta'").fetchone():
            for sql in DDL:
                store.conn.execute(sql)
            store.conn.execute("INSERT INTO notification_meta VALUES(1,?)", (uuid4().hex,))
        rows = store.conn.execute("SELECT version,namespace FROM notification_meta").fetchall()
        require(len(rows) == 1 and rows[0][0] == 1, "NOTIFICATION_SCHEMA_MISMATCH", "Unsupported notification schema.")


def safe_label(value, fallback, limit=160, *, markdown=True):
    if not isinstance(value, str) or not value.strip():
        return fallback
    value = re.sub(r"https?://\S+", "[enlace omitido]", value, flags=re.I)
    value = re.sub(r"(?:[A-Za-z]:[\\/]|\\\\)\S+", "[ruta omitida]", value)
    value = "".join(c if not unicodedata.category(c).startswith("C") else " " for c in value)
    value = " ".join(value.split())[:limit]
    value = value.replace("@", "＠").replace("<", "‹").replace(">", "›")
    return (re.sub(r"([\\\x60*_~|[\]])", r"\\\1", value) if markdown else value) or fallback


def enqueue(store, source_event_id, topic, kind, event, created_at=None):
    require(kind in NOTIFIABLE | {"CONNECTION_TEST"}, "INVALID_NOTIFICATION_TYPE", "Unsupported notification type.")
    require(kind != "CONNECTION_TEST" or store.storage_mode == "SYNTHETIC_ONLY",
            "SYNTHETIC_ONLY", "Connection tests must use a separate synthetic database.")
    store.conn.execute("""INSERT INTO notifications
        (notification_id,source_event_id,host,topic_id,type,created_at,status,event_json)
        VALUES(?,?,?,?,?,?,'PENDING',?) ON CONFLICT(source_event_id) DO NOTHING""",
        (uuid4().hex, source_event_id, topic["host"], topic["topic_id"], kind, created_at or now(), json_text(event)))


def collect(store):
    """Project persisted records. No forum body, draft, prompt or error detail is read."""
    initialize(store)
    with store.transaction():
        before = store.conn.execute("SELECT count(*) FROM notifications").fetchone()[0]
        tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "evaluation_runs" in tables:
            runs = store.conn.execute("""SELECT r.run_id,r.host,r.topic_id,r.decision,r.completed_at
                FROM evaluation_runs r WHERE r.completed_at IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM notifications n WHERE n.source_event_id='evaluation:'||r.run_id)
                ORDER BY r.completed_at,r.run_id""").fetchall()
            for run in runs:
                if run["decision"] not in NOTIFIABLE:
                    continue
                changes = store.conn.execute("""SELECT p.capture_pk,m.author_id,
                    json_extract(cm.metadata_json,'$.author_name_observed') AS author
                    FROM evaluation_jobs j JOIN pending_changes p ON p.id=j.change_id
                    JOIN messages m ON m.host=p.host AND m.topic_id=p.topic_id AND m.message_id=p.message_id
                    JOIN capture_messages cm ON cm.capture_pk=p.capture_pk AND cm.message_id=p.message_id
                    WHERE j.run_id=? ORDER BY p.capture_pk,p.ordinal,p.id""", (run["run_id"],)).fetchall()
                title = author = None
                if changes:
                    latest = changes[-1]
                    title_row = store.conn.execute("SELECT json_extract(source_json,'$.metadata.title_observed') FROM captures WHERE id=?",
                                                   (latest["capture_pk"],)).fetchone()
                    title = title_row[0] if title_row else None
                    author = latest["author"] or f"Cuenta {latest['author_id']}"
                draft = store.conn.execute("SELECT id FROM narrative_drafts WHERE run_id=?", (run["run_id"],)).fetchone()
                event = {"title": safe_label(title, "Título no observado", markdown=False),
                         "author": safe_label(author, "Autor no identificado", 80, markdown=False),
                         "change_count": len(changes), "draft_id": draft[0] if draft else None,
                         "reader_issue": False}
                enqueue(store, "evaluation:" + run["run_id"], run, run["decision"], event, run["completed_at"])
            # stale_reason survives retirement, so the transition remains observable.
            for draft in store.conn.execute("""SELECT id,host,topic_id FROM narrative_drafts
                WHERE stale_reason IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM notifications n WHERE n.source_event_id='draft:'||narrative_drafts.id||':STALE')""").fetchall():
                enqueue(store, "draft:" + draft["id"] + ":STALE", draft, "STALE",
                        {"title": "Tema " + str(draft["topic_id"]), "author": None, "change_count": 0,
                         "draft_id": draft["id"], "reader_issue": False})
        consumed = ""
        if "workflow_incidents" in tables:
            consumed = " AND NOT EXISTS(SELECT 1 FROM workflow_incidents w WHERE w.import_error_id=e.id)"
            for incident in store.conn.execute("""SELECT w.* FROM workflow_incidents w WHERE NOT EXISTS(
                SELECT 1 FROM notifications n WHERE n.source_event_id='workflow-incident:'||w.incident_id)""").fetchall():
                enqueue(store, "workflow-incident:" + incident["incident_id"], incident, incident["type"],
                        {"title": "Tema " + str(incident["topic_id"]), "author": None, "change_count": 0,
                         "draft_id": None, "reader_issue": True,
                         "session_unverified": incident["cause_code"] != "SESSION_EXPIRED"}, incident["created_at"])
        for error in store.conn.execute("""SELECT e.id,e.host,e.topic_id,e.code,e.recorded_at FROM import_errors e
            JOIN topics t ON t.host=e.host AND t.topic_id=e.topic_id WHERE NOT EXISTS(
            SELECT 1 FROM notifications n WHERE n.source_event_id='reader-error:'||e.id)""" + consumed + " ORDER BY e.id").fetchall():
            kind = READER_TYPES.get(error["code"])
            if kind:
                enqueue(store, "reader-error:" + str(error["id"]), error, kind,
                        {"title": "Tema " + str(error["topic_id"]), "author": None, "change_count": 0,
                         "draft_id": None, "reader_issue": True}, error["recorded_at"])
        added = store.conn.execute("SELECT count(*) FROM notifications").fetchone()[0] - before
    return {"queued": added}


def payload(store, row):
    event = load_json(row["event_json"])
    link = store._link(f"https://{row['host']}/index.php?showtopic={row['topic_id']}")
    if row["type"] == "CONNECTION_TEST":
        require(store.storage_mode == "SYNTHETIC_ONLY", "SYNTHETIC_ONLY", "Test event in a real database is rejected.")
        content = CONNECTION_TEST
    else:
        title, state = LABELS[row["type"]]
        if row["type"] == "SESSION_EXPIRED" and event.get("session_unverified"):
            state = "No se pudo verificar la sesión; inicia o revisa la sesión manualmente"
        lines = ["PRUEBA / DATOS SINTÉTICOS"] if store.storage_mode == "SYNTHETIC_ONLY" else []
        lines.extend(["Nozomu — " + title, "", "Tema: " + safe_label(event.get("title"), "Título no observado")])
        if row["type"] == "DRAFT_READY":
            lines.append("Autor de la actualización: " + safe_label(event.get("author"), "Autor no identificado", 80))
        if row["type"] == "STALE":
            lines.append("El borrador preparado ha dejado de estar vigente.")
        if event.get("reader_issue") and row["type"] == "NEEDS_HUMAN_REVIEW":
            lines.append("No se pudo verificar la lectura o la identidad de sesión; no se confirma la causa.")
        lines.append("Estado: " + state)
        count = event.get("change_count", 0)
        if type(count) is int and count > 1:
            lines.append("Novedades agrupadas en esta evaluación: " + str(count))
        lines.extend(["Tema: <" + link.canonical_url + ">", "",
                      "No se ha publicado ningún mensaje en Naruto Rol."])
        content = "\n".join(lines)
    require(len(content.encode("utf-16-le")) // 2 <= 2000, "NOTIFICATION_TOO_LARGE", "Notification exceeds Discord's content budget.")
    return {"content": content, "allowed_mentions": {"parse": []}, "flags": 4}


def list_notifications(store, *, preview=False):
    initialize(store)
    rows = [dict(r) for r in store.conn.execute("SELECT * FROM notifications ORDER BY created_at,notification_id")]
    for row in rows:
        if preview:
            row["payload"] = payload(store, row)
        row.pop("event_json")
    return rows


def connection_test(store):
    require(store.storage_mode == "SYNTHETIC_ONLY", "SYNTHETIC_ONLY", "Tests must use a separate synthetic database.")
    initialize(store)
    link = store._link("https://narutorol.jcink.net/index.php?showtopic=275")
    with store.transaction():
        enqueue(store, "manual-test:connection:v1", store._topic(link), "CONNECTION_TEST", {})
    return list_notifications(store, preview=True)


def retry_configuration_failure(store, notification_id):
    initialize(store)
    allowed = {"DISCORD_SECRET_UNAVAILABLE", "TLS_VERIFICATION_FAILED", "DISCORD_REDIRECT_REJECTED",
               "DISCORD_HTTP_400", "DISCORD_HTTP_401", "DISCORD_HTTP_403", "DISCORD_HTTP_404"}
    with store.transaction():
        row = store.conn.execute("SELECT * FROM notifications WHERE notification_id=?", (notification_id,)).fetchone()
        require(row is not None and row["status"] == "FAILED_FINAL" and row["last_error"] in allowed
                and not row["delivery_uncertain"] and row["attempt_count"] < MAX_ATTEMPTS,
                "NOTIFICATION_RETRY_REJECTED", "Only definite configuration failures below the lifetime attempt limit can be retried manually.")
        store.conn.execute("UPDATE notifications SET status='PENDING',next_attempt_at=0 WHERE notification_id=?", (notification_id,))
    return {"notification_id": notification_id, "status": "PENDING", "attempt_count_preserved": True}


def control_root():
    require(os.name == "nt" and os.environ.get("LOCALAPPDATA"), "WINDOWS_CREDENTIALS_REQUIRED",
            "Default Discord delivery control requires the current Windows user.")
    return Path(os.environ["LOCALAPPDATA"]) / "NozomuForumWatch" / "discord-delivery"


@contextmanager
def delivery_lock(folder):
    folder = Path(folder).resolve()
    require(not folder.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Delivery control must be outside the character tree.")
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "delivery.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            require(False, "NOTIFICATION_BUSY", "Another manual Discord delivery is running.")
        try:
            yield folder
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds")


def send_pending(store, transport=None, *, limit=10, timer=time.time, control=None):
    require(type(limit) is int and 1 <= limit <= 20, "INVALID_NOTIFICATION_LIMIT", "Manual batch limit must be 1 to 20.")
    collect(store)
    with delivery_lock(control if control is not None else control_root()) as folder:
        from .discord import Delivery, DiscordTransport, seconds
        checkpoint = folder / "cooldown.json"
        wait_until = 0
        if checkpoint.exists():
            state = load_json(checkpoint.read_text(encoding="utf-8"))
            require(set(state) == {"blocked_until"} and isinstance(state["blocked_until"], (int, float)),
                    "INVALID_DISCORD_CONTROL", "Delivery checkpoint is invalid; no send attempted.")
            wait_until = state["blocked_until"]
            require(0 <= wait_until < 253402300799, "INVALID_DISCORD_CONTROL", "Delivery checkpoint is invalid.")
        with store.transaction():
            for row in store.conn.execute("SELECT notification_id FROM notifications WHERE status='SENDING'").fetchall():
                store.conn.execute("""UPDATE notifications SET status='FAILED_FINAL',last_error='INTERRUPTED_UNCERTAIN',
                    delivery_uncertain=1 WHERE notification_id=?""", (row[0],))
                store.conn.execute("""UPDATE notification_attempts SET status='FAILED_FINAL',error='INTERRUPTED_UNCERTAIN',
                    finished_at=? WHERE notification_id=? AND status='SENDING'""", (stamp(timer()), row[0]))
        if wait_until > timer():
            return {"result": "WAIT_RETRY_AFTER", "blocked_until": stamp(wait_until), "attempted": 0, "notifications": []}
        eligible = store.conn.execute("""SELECT * FROM notifications WHERE status IN ('PENDING','FAILED_RETRYABLE')
            AND attempt_count<? AND next_attempt_at<=? ORDER BY created_at,notification_id LIMIT ?""",
                                      (MAX_ATTEMPTS, timer(), limit)).fetchall()
        results = []
        sender = transport
        for record in eligible:
            row = dict(record)
            if row["type"] == "DRAFT_READY":
                event = load_json(row["event_json"])
                active = store.conn.execute("SELECT 1 FROM narrative_drafts WHERE id=? AND lifecycle='ACTIVE'",
                                            (event.get("draft_id"),)).fetchone()
                if not active:
                    with store.transaction():
                        store.conn.execute("UPDATE notifications SET status='SUPERSEDED',last_error='DRAFT_NO_LONGER_ACTIVE' WHERE notification_id=?",
                                           (row["notification_id"],))
                    results.append({"notification_id": row["notification_id"], "status": "SUPERSEDED", "attempted": False})
                    continue
            outgoing = payload(store, row)
            attempt = row["attempt_count"] + 1
            started = stamp(timer())
            with store.transaction():
                store.conn.execute("""UPDATE notifications SET status='SENDING',attempt_count=?,last_attempt_at=?
                    WHERE notification_id=?""", (attempt, started, row["notification_id"]))
                store.conn.execute("INSERT INTO notification_attempts VALUES(?,?,?,NULL,'SENDING',NULL)",
                                   (row["notification_id"], attempt, started))
            try:
                if sender is None:
                    sender = DiscordTransport()
                outcome = sender.send(outgoing)
                require(isinstance(outcome, Delivery) and outcome.status in {"SENT", "FAILED_RETRYABLE", "FAILED_FINAL"},
                        "INVALID_DELIVERY_RESULT", "Unknown delivery result.")
            except Exception:
                outcome = Delivery("FAILED_FINAL", "TRANSPORT_FAILURE_UNCERTAIN", uncertain=True, stop_batch=True)
            finished = timer()
            status, error = outcome.status, outcome.error
            if status == "FAILED_RETRYABLE" and attempt >= MAX_ATTEMPTS:
                status, error = "FAILED_FINAL", "ATTEMPTS_EXHAUSTED"
            delay = seconds(outcome.retry_after) or 0
            if delay:
                temporary = folder / ("cooldown-" + uuid4().hex + ".tmp")
                temporary.write_text(json_text({"blocked_until": finished + delay}), encoding="utf-8")
                temporary.replace(checkpoint)
            next_attempt = finished + max(delay, 2 ** attempt) if status == "FAILED_RETRYABLE" else 0
            with store.transaction():
                store.conn.execute("""UPDATE notifications SET status=?,last_error=?,remote_message_id=?,
                    next_attempt_at=?,delivery_uncertain=? WHERE notification_id=?""",
                    (status, error, outcome.remote_message_id, next_attempt, int(outcome.uncertain), row["notification_id"]))
                store.conn.execute("""UPDATE notification_attempts SET status=?,error=?,finished_at=?
                    WHERE notification_id=? AND attempt=?""", (status, error, stamp(finished), row["notification_id"], attempt))
            results.append({"notification_id": row["notification_id"], "source_event_id": row["source_event_id"],
                            "type": row["type"], "status": status, "attempt_count": attempt,
                            "remote_message_id": outcome.remote_message_id, "last_error": error,
                            "delivery_uncertain": outcome.uncertain,
                            "next_attempt_at": stamp(next_attempt) if next_attempt else None, "attempted": True})
            if delay or outcome.stop_batch:
                break
        return {"result": "MANUAL_BATCH_COMPLETE", "attempted": sum(r["attempted"] for r in results), "notifications": results}
