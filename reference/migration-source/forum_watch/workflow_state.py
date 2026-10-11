"""Additive operational barriers; original topic intent and capture schema remain intact."""

from uuid import uuid4

from .models import require
from .store import now

DDL = (
    "CREATE TABLE workflow_meta(version INTEGER NOT NULL CHECK(version=1))",
    """CREATE TABLE workflow_topic_blocks(
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, blocked_state TEXT NOT NULL
        CHECK(blocked_state IN ('NEEDS_LOGIN','ACCESS_DENIED')),
        incident_id TEXT NOT NULL, blocked_at TEXT NOT NULL,
        PRIMARY KEY(host,topic_id), FOREIGN KEY(host,topic_id) REFERENCES topics(host,topic_id))""",
    """CREATE TABLE workflow_incidents(
        incident_id TEXT PRIMARY KEY, host TEXT NOT NULL, topic_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('SESSION_EXPIRED','ACCESS_DENIED')),
        cause_code TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT,
        import_error_id INTEGER UNIQUE,
        FOREIGN KEY(host,topic_id) REFERENCES topics(host,topic_id),
        FOREIGN KEY(import_error_id) REFERENCES import_errors(id))""",
)


def installed(store):
    return store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_meta' AND type='table'").fetchone() is not None


def initialize(store):
    with store.transaction():
        if not installed(store):
            for sql in DDL:
                store.conn.execute(sql)
            store.conn.execute("INSERT INTO workflow_meta VALUES(1)")
        values = store.conn.execute("SELECT version FROM workflow_meta").fetchall()
        require(len(values) == 1 and values[0][0] == 1, "WORKFLOW_SCHEMA_MISMATCH", "Unsupported workflow component.")


def effective_topic(store, topic):
    result = dict(topic)
    if installed(store):
        block = store.conn.execute("SELECT blocked_state,incident_id,blocked_at FROM workflow_topic_blocks WHERE host=? AND topic_id=?",
                                   (topic["host"], topic["topic_id"])).fetchone()
        if block:
            result["tracking_intent"] = result["state"]
            result["block"] = dict(block)
            if result["state"] == "ACTIVE":
                result["state"] = block["blocked_state"]
    return result


def clear_block(store, link):
    """Caller owns the state-change transaction; resume is always explicit."""
    if not installed(store):
        return
    rows = store.conn.execute("SELECT incident_id FROM workflow_topic_blocks WHERE host=? AND topic_id=?",
                              (link.host, link.topic_id)).fetchall()
    for row in rows:
        store.conn.execute("UPDATE workflow_incidents SET resolved_at=? WHERE incident_id=?", (now(), row[0]))
    store.conn.execute("DELETE FROM workflow_topic_blocks WHERE host=? AND topic_id=?", (link.host, link.topic_id))


def block_topic(store, link, code, import_error_id=None):
    state = "ACCESS_DENIED" if code in {"ACCESS_DENIED", "WRONG_ACCOUNT"} else "NEEDS_LOGIN"
    kind = "ACCESS_DENIED" if state == "ACCESS_DENIED" else "SESSION_EXPIRED"
    with store.transaction():
        old = store.conn.execute("SELECT incident_id FROM workflow_topic_blocks WHERE host=? AND topic_id=?",
                                 (link.host, link.topic_id)).fetchone()
        if old:
            return old[0]
        incident = uuid4().hex
        created = now()
        store.conn.execute("INSERT INTO workflow_incidents VALUES(?,?,?,?,?,?,NULL,?)",
                           (incident, link.host, link.topic_id, kind, code, created, import_error_id))
        store.conn.execute("INSERT INTO workflow_topic_blocks VALUES(?,?,?,?,?)",
                           (link.host, link.topic_id, state, incident, created))
    return incident

