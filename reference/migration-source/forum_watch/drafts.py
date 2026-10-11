"""Operational draft ledger in the existing SQLite DB; character files untouched."""

from contextlib import contextmanager
from pathlib import Path
import sys
from uuid import uuid4

from .models import WatchError, digest, json_text, load_json, require
from .store import WORKSPACE, now

DDL = (
    "CREATE TABLE narrative_meta (version INTEGER NOT NULL CHECK(version=1), namespace TEXT NOT NULL)",
    """CREATE TABLE evaluation_runs (
        run_id TEXT PRIMARY KEY, host TEXT NOT NULL, topic_id INTEGER NOT NULL,
        created_at TEXT NOT NULL, completed_at TEXT, decision TEXT NOT NULL,
        reason TEXT NOT NULL, context_hash TEXT, context_json TEXT, source_versions_json TEXT,
        result_json TEXT, model_called INTEGER NOT NULL CHECK(model_called IN (0,1)),
        FOREIGN KEY(host,topic_id) REFERENCES topics(host,topic_id))""",
    """CREATE TABLE evaluation_jobs (
        change_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, decision TEXT NOT NULL,
        FOREIGN KEY(change_id) REFERENCES pending_changes(id),
        FOREIGN KEY(run_id) REFERENCES evaluation_runs(run_id))""",
    """CREATE TABLE narrative_drafts (
        id TEXT PRIMARY KEY, host TEXT NOT NULL, topic_id INTEGER NOT NULL, version INTEGER NOT NULL,
        run_id TEXT NOT NULL, created_at TEXT NOT NULL,
        review_status TEXT NOT NULL CHECK(review_status='PENDING_HUMAN_REVIEW'),
        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('ACTIVE','STALE','RETIRED')),
        stale_reason TEXT, file_path TEXT NOT NULL UNIQUE, file_hash TEXT NOT NULL,
        manual_edited INTEGER NOT NULL DEFAULT 0, dependencies_json TEXT NOT NULL,
        source_versions_json TEXT NOT NULL, UNIQUE(host,topic_id,version),
        FOREIGN KEY(run_id) REFERENCES evaluation_runs(run_id))""",
    "CREATE UNIQUE INDEX one_active_draft ON narrative_drafts(host,topic_id) WHERE lifecycle='ACTIVE'",
    """CREATE TABLE draft_file_revisions (
        draft_id TEXT NOT NULL, revision INTEGER NOT NULL, observed_at TEXT NOT NULL,
        origin TEXT NOT NULL CHECK(origin IN ('GENERATED','MANUAL')), text TEXT NOT NULL, sha256 TEXT NOT NULL,
        PRIMARY KEY(draft_id,revision), FOREIGN KEY(draft_id) REFERENCES narrative_drafts(id))""",
)


def installed(store):
    return store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='narrative_meta'").fetchone() is not None


def initialize(store):
    with store.transaction():
        if not installed(store):
            for sql in DDL:
                store.conn.execute(sql)
            store.conn.execute("INSERT INTO narrative_meta VALUES(1,?)", (uuid4().hex,))
        rows = store.conn.execute("SELECT version,namespace FROM narrative_meta").fetchall()
        require(len(rows) == 1 and rows[0][0] == 1, "NARRATIVE_SCHEMA_MISMATCH", "Unsupported narrative component schema.")


def draft_root(store):
    namespace = store.conn.execute("SELECT namespace FROM narrative_meta").fetchone()[0]
    require(len(namespace) == 32 and all(c in "0123456789abcdef" for c in namespace), "INVALID_DRAFT_PATH", "Invalid operational namespace.")
    path = (store.path.parent / "forum-watch-drafts" / namespace).resolve()
    require(not path.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Operational drafts must be outside the character tree.")
    return path


@contextmanager
def evaluation_lock(store):
    root = draft_root(store)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".evaluation.lock").open("a+b") as handle:
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
        except OSError as exc:
            raise WatchError("EVALUATION_BUSY", "Another manual evaluation is running.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def dependencies(store, link):
    return [{"message_id": r[0], "revision": r[1]} for r in store.conn.execute(
        "SELECT message_id,revision FROM capture_messages WHERE capture_pk=? ORDER BY ordinal",
        (store._topic(link)["last_capture_pk"],))]


def invalidate(store, link):
    """Called inside the existing capture transaction, so invalidation is atomic."""
    if not installed(store):
        return
    current = dependencies(store, link)
    for row in store.conn.execute("SELECT id,dependencies_json FROM narrative_drafts WHERE host=? AND topic_id=? AND lifecycle='ACTIVE'",
                                  (link.host, link.topic_id)).fetchall():
        if load_json(row["dependencies_json"]) != current or store._topic(link)["state"] == "CLOSED":
            store.conn.execute("UPDATE narrative_drafts SET lifecycle='STALE',stale_reason='CONTEXT_CHANGED' WHERE id=?", (row["id"],))


def observe_manual_edits(store, link):
    root = draft_root(store)
    for row in store.conn.execute("SELECT * FROM narrative_drafts WHERE host=? AND topic_id=?", (link.host, link.topic_id)).fetchall():
        path = Path(row["file_path"])
        require(not path.is_symlink() and path.resolve().parent == root,
                "INVALID_DRAFT_PATH", "Draft path escaped the operational directory.")
        if not path.is_file():
            store.conn.execute("UPDATE narrative_drafts SET lifecycle='STALE',stale_reason='FILE_MISSING' WHERE id=? AND lifecycle!='RETIRED'", (row["id"],))
            continue
        require(path.stat().st_size <= 2_000_000, "DRAFT_FILE_TOO_LARGE", "Manual draft exceeds the observation budget; file is preserved.")
        text = path.read_bytes().decode("utf-8")
        hashed = digest(text)
        if hashed != row["file_hash"]:
            version = store.conn.execute("SELECT max(revision)+1 FROM draft_file_revisions WHERE draft_id=?", (row["id"],)).fetchone()[0]
            store.conn.execute("INSERT INTO draft_file_revisions VALUES(?,?,?,?,?,?)", (row["id"], version, now(), "MANUAL", text, hashed))
            store.conn.execute("UPDATE narrative_drafts SET file_hash=?,manual_edited=1 WHERE id=?", (hashed, row["id"]))


def pending_draft(store, link):
    return store.conn.execute("SELECT 1 FROM narrative_drafts WHERE host=? AND topic_id=? AND lifecycle!='RETIRED' LIMIT 1",
                              (link.host, link.topic_id)).fetchone() is not None


def persist(store, link, run_id, package, text):
    root = draft_root(store)
    root.mkdir(parents=True, exist_ok=True)
    version = store.conn.execute("SELECT coalesce(max(version),0)+1 FROM narrative_drafts WHERE host=? AND topic_id=?", (link.host, link.topic_id)).fetchone()[0]
    draft_id = uuid4().hex
    path = root / f"topic-{link.topic_id}-v{version}-{draft_id}.md"
    content = f"# Borrador del tema {link.topic_id} — versión {version}\n\nPENDING_HUMAN_REVIEW. No publicado ni canónico. Consultar estado actual con la CLI.\n\n{text}\n"
    # Exclusive creation: no model text, ID or path can overwrite an existing file.
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(content)
    artifact = {"draft_id": draft_id, "version": version, "path": str(path), "sha256": digest(content),
                "status": "PENDING_HUMAN_REVIEW", "lifecycle": "ACTIVE"}
    try:
        store.conn.execute("""INSERT INTO narrative_drafts
            (id,host,topic_id,version,run_id,created_at,review_status,lifecycle,file_path,file_hash,dependencies_json,source_versions_json)
            VALUES(?,?,?,?,?,?,'PENDING_HUMAN_REVIEW','ACTIVE',?,?,?,?)""",
            (draft_id, link.host, link.topic_id, version, run_id, now(), str(path), digest(content),
             json_text([{"message_id": m["message_id"], "revision": m["revision"]} for m in package["SCENE"]["messages"]]), json_text(package["source_versions"])))
        store.conn.execute("INSERT INTO draft_file_revisions VALUES(?,1,?,'GENERATED',?,?)", (draft_id, now(), content, digest(content)))
    except Exception:
        if path.read_bytes() == content.encode("utf-8"):
            path.unlink()
        raise
    return artifact


def cleanup_uncommitted(store, artifact):
    if store.conn.execute("SELECT 1 FROM narrative_drafts WHERE id=?", (artifact["draft_id"],)).fetchone():
        return
    path = Path(artifact["path"])
    require(not path.is_symlink() and path.resolve().parent == draft_root(store), "INVALID_DRAFT_PATH", "Refusing cleanup outside the operational directory.")
    # Only this invocation's unchanged, uncommitted file can be removed. A
    # concurrent human edit is preserved even if the DB transaction failed.
    if path.is_file() and digest(path.read_bytes().decode("utf-8")) == artifact["sha256"]:
        path.unlink()


def list_drafts(store, url):
    initialize(store)
    link = store._link(url)
    with evaluation_lock(store), store.transaction():
        observe_manual_edits(store, link)
        invalidate(store, link)
        return [dict(r) for r in store.conn.execute("SELECT * FROM narrative_drafts WHERE host=? AND topic_id=? ORDER BY version", (link.host, link.topic_id))]


def retire(store, url, draft_id):
    initialize(store)
    link = store._link(url)
    with evaluation_lock(store), store.transaction():
        observe_manual_edits(store, link)
        row = store.conn.execute("SELECT id FROM narrative_drafts WHERE host=? AND topic_id=? AND id=?", (link.host, link.topic_id, draft_id)).fetchone()
        require(row is not None, "DRAFT_NOT_FOUND", "Draft does not belong to the selected topic.")
        store.conn.execute("UPDATE narrative_drafts SET lifecycle='RETIRED' WHERE id=?", (draft_id,))
    return {"draft_id": draft_id, "lifecycle": "RETIRED", "review_status": "PENDING_HUMAN_REVIEW", "files_preserved": True}
