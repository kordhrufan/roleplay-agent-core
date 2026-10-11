"""Shared transactional observations with explicit, physically separate origins."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .models import (Capture, REAL_STORAGE_MODE, SCHEMA_VERSION, Settings, WatchError,
                     json_text, load_json, normalize_url, require)


APPLICATION_ID = 0x46575331
WORKSPACE = Path(__file__).resolve().parent.parent
PROTECTED = (".codex", ".git", "instructions", "reference", "shared", "memory", "drafts")

DDL = (
    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE topics (
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, original_url TEXT NOT NULL,
        canonical_url TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('PAUSED','ACTIVE','CLOSED')),
        title TEXT, participants TEXT, scene_classification TEXT, memory_topic_path TEXT,
        last_processed_message_id TEXT, last_capture_pk INTEGER,
        PRIMARY KEY(host, topic_id), FOREIGN KEY(last_capture_pk) REFERENCES captures(id))""",
    """CREATE TABLE captures (
        id INTEGER PRIMARY KEY, host TEXT NOT NULL, topic_id INTEGER NOT NULL,
        capture_id TEXT NOT NULL, captured_at TEXT NOT NULL, imported_at TEXT NOT NULL,
        origin TEXT NOT NULL CHECK(origin='SYNTHETIC'), complete INTEGER NOT NULL CHECK(complete=1),
        kind TEXT NOT NULL CHECK(kind IN ('BASELINE','UPDATE')),
        source_hash TEXT NOT NULL, source_json TEXT NOT NULL, new_count INTEGER NOT NULL,
        edit_count INTEGER NOT NULL, UNIQUE(host, topic_id, capture_id),
        FOREIGN KEY(host, topic_id) REFERENCES topics(host, topic_id))""",
    """CREATE TABLE messages (
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, message_id TEXT NOT NULL,
        author_id INTEGER NOT NULL, current_revision INTEGER NOT NULL,
        PRIMARY KEY(host, topic_id, message_id),
        FOREIGN KEY(host, topic_id) REFERENCES topics(host, topic_id))""",
    """CREATE TABLE revisions (
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, message_id TEXT NOT NULL,
        revision INTEGER NOT NULL, capture_pk INTEGER NOT NULL, content TEXT NOT NULL,
        normalized_content TEXT NOT NULL, content_hash TEXT NOT NULL,
        PRIMARY KEY(host, topic_id, message_id, revision),
        FOREIGN KEY(host, topic_id, message_id) REFERENCES messages(host, topic_id, message_id),
        FOREIGN KEY(capture_pk) REFERENCES captures(id))""",
    """CREATE TABLE capture_messages (
        capture_pk INTEGER NOT NULL, ordinal INTEGER NOT NULL,
        host TEXT NOT NULL, topic_id INTEGER NOT NULL, message_id TEXT NOT NULL,
        revision INTEGER NOT NULL, metadata_json TEXT NOT NULL,
        PRIMARY KEY(capture_pk, ordinal), UNIQUE(capture_pk, message_id),
        FOREIGN KEY(capture_pk) REFERENCES captures(id),
        FOREIGN KEY(host, topic_id, message_id, revision)
            REFERENCES revisions(host, topic_id, message_id, revision))""",
    """CREATE TABLE pending_changes (
        id INTEGER PRIMARY KEY, host TEXT NOT NULL, topic_id INTEGER NOT NULL,
        capture_pk INTEGER NOT NULL, ordinal INTEGER NOT NULL, message_id TEXT NOT NULL,
        revision INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('NEW_MESSAGE','CONTENT_EDIT')),
        is_own INTEGER NOT NULL CHECK(is_own IN (0,1)),
        state TEXT NOT NULL CHECK(state='PENDING_EVALUATION'),
        UNIQUE(host, topic_id, message_id, revision),
        FOREIGN KEY(capture_pk) REFERENCES captures(id),
        FOREIGN KEY(host, topic_id, message_id, revision)
            REFERENCES revisions(host, topic_id, message_id, revision))""",
    """CREATE TABLE import_errors (
        id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, host TEXT, topic_id INTEGER,
        capture_id TEXT, code TEXT NOT NULL, message TEXT NOT NULL, details_json TEXT NOT NULL)""",
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def database_path(value):
    require(bool(value) and str(value) != ":memory:", "INVALID_DB_PATH", "An explicit database file path is required.")
    path = Path(value).expanduser().resolve()
    require(path.suffix.lower() in {".sqlite3", ".sqlite", ".db"}, "INVALID_DB_PATH", "Use a .sqlite3, .sqlite or .db file.")
    require(path.parent.is_dir(), "INVALID_DB_PATH", "Database parent directory must already exist.")
    require(not any(path.is_relative_to((WORKSPACE / name).resolve()) for name in PROTECTED),
            "PROTECTED_PATH", "Database path is inside a protected project directory.")
    return path


class Store:
    def __init__(self, path, settings=None, *, create=False, storage_mode="SYNTHETIC_ONLY"):
        self.path = database_path(path)
        require(storage_mode in {"SYNTHETIC_ONLY", REAL_STORAGE_MODE}, "INVALID_STORAGE_MODE", "Unsupported storage mode.")
        self.storage_mode = storage_mode
        real = storage_mode == REAL_STORAGE_MODE
        require(not real or not self.path.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH",
                "Real operational data must be outside the project and narrative context directory.")
        schema_version = 2 if real else SCHEMA_VERSION
        require(create or self.path.is_file(), "DB_NOT_FOUND", "Initialize an explicit synthetic database first.")
        self.conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        try:
            with self.transaction():
                tables = {row[0] for row in self.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                app_id = self.conn.execute("PRAGMA application_id").fetchone()[0]
                version = self.conn.execute("PRAGMA user_version").fetchone()[0]
                if not tables and not app_id and not version and create:
                    chosen = settings or Settings()
                    for sql in DDL:
                        self.conn.execute(sql.replace("CHECK(origin='SYNTHETIC')", "CHECK(origin='AUTHENTICATED_FORUM')") if real else sql)
                    stored_metadata = dict(chosen.metadata(), storage_mode=storage_mode)
                    self.conn.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", stored_metadata.items())
                    self.conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    self.conn.execute(f"PRAGMA user_version={schema_version}")
                else:
                    require(app_id == APPLICATION_ID and version == schema_version and "metadata" in tables,
                            "INCOMPATIBLE_DB", "Database is unmarked or has an unsupported storage schema.")
                metadata = dict(self.conn.execute("SELECT key,value FROM metadata"))
                chosen = Settings(metadata.get("authorized_host"), int(metadata.get("expected_account_id", "0")),
                                  int(metadata.get("poll_interval_seconds", "0")), metadata.get("forum_permission"))
                require(metadata == dict(chosen.metadata(), storage_mode=storage_mode),
                        "INCOMPATIBLE_DB", "Database origin does not match the explicitly selected mode.")
                require(not real or chosen.expected_account_id == 59, "CONFIG_MISMATCH", "Real reader requires account 59.")
                require(settings is None or chosen == settings, "CONFIG_MISMATCH", "Configuration differs from the stored settings.")
                self.settings = chosen
        except Exception:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _link(self, url):
        link = normalize_url(url, self.settings.authorized_host)
        require(self.storage_mode != REAL_STORAGE_MODE or link.topic_id == 275,
                "UNAUTHORIZED_TOPIC", "Real reader is authorized only for topic 275.")
        return link

    def _topic(self, link):
        row = self.conn.execute("SELECT * FROM topics WHERE host=? AND topic_id=?",
                                (link.host, link.topic_id)).fetchone()
        require(row is not None, "UNAUTHORIZED_TOPIC", "Topic must be added explicitly before importing.")
        return row

    def add(self, url):
        link = self._link(url)
        with self.transaction():
            self.conn.execute("""INSERT INTO topics(host,topic_id,original_url,canonical_url,state)
                VALUES (?,?,?,?,'PAUSED') ON CONFLICT(host,topic_id) DO NOTHING""",
                              (link.host, link.topic_id, link.original_url, link.canonical_url))
        return self.inspect(url)

    def list_topics(self):
        from .workflow_state import effective_topic
        return [effective_topic(self, row) for row in self.conn.execute("SELECT * FROM topics ORDER BY host,topic_id")]

    def inspect(self, url):
        from .workflow_state import effective_topic
        link = self._link(url)
        result = effective_topic(self, self._topic(link))
        latest = self.conn.execute("SELECT capture_id,captured_at,kind FROM captures WHERE id=?",
                                   (result.pop("last_capture_pk"),)).fetchone()
        result["last_valid_capture"] = dict(latest) if latest else None
        result["pending_count"] = len(self.pending(url))
        result["storage_mode"] = self.storage_mode
        result["expected_account_id"] = self.settings.expected_account_id
        result["session_identity_status"] = "NOT_VERIFIED"
        result["poll_interval_seconds"] = self.settings.poll_interval_seconds
        result["forum_permission"] = self.settings.forum_permission
        result["scheduled_service"] = False
        from . import workflow_state
        if workflow_state.installed(self):
            result["scheduled_service"] = None
            result["scheduler_status"] = "NOT_QUERIED; use scheduler status"
        return result

    def set_state(self, url, state):
        require(state in {"PAUSED", "ACTIVE", "CLOSED"}, "INVALID_STATE", "Unsupported topic state.")
        link = self._link(url)
        with self.transaction():
            topic = self._topic(link)
            require(topic["state"] != "CLOSED" or state == "CLOSED",
                    "TOPIC_CLOSED", "Closed topics are retained and cannot be resumed in this milestone.")
            self.conn.execute("UPDATE topics SET state=? WHERE host=? AND topic_id=?",
                              (state, link.host, link.topic_id))
            from .drafts import invalidate
            invalidate(self, link)
            from .workflow_state import clear_block
            clear_block(self, link)
        return self.inspect(url)

    def versions(self, url, message_id=None):
        link = self._link(url)
        self._topic(link)
        sql = """SELECT r.message_id,m.author_id,r.revision,r.content,r.normalized_content,
                 r.content_hash,c.capture_id,c.origin FROM revisions r JOIN messages m
                 USING(host,topic_id,message_id) JOIN captures c ON c.id=r.capture_pk
                 WHERE r.host=? AND r.topic_id=?"""
        args = [link.host, link.topic_id]
        if message_id is not None:
            sql += " AND r.message_id=?"
            args.append(message_id)
        return [dict(row, is_own=row["author_id"] == self.settings.expected_account_id)
                for row in self.conn.execute(sql + " ORDER BY r.capture_pk,r.message_id,r.revision", args)]

    def pending(self, url):
        link = self._link(url)
        self._topic(link)
        from .drafts import installed
        unevaluated = " AND NOT EXISTS(SELECT 1 FROM evaluation_jobs j WHERE j.change_id=p.id)" if installed(self) else ""
        rows = self.conn.execute("""SELECT p.id,c.capture_id,p.ordinal,p.message_id,p.revision,p.kind,
            p.is_own,p.state,c.origin FROM pending_changes p JOIN captures c ON c.id=p.capture_pk
            WHERE p.host=? AND p.topic_id=?""" + unevaluated + " ORDER BY p.capture_pk,p.ordinal,p.id", (link.host, link.topic_id))
        return [dict(row, is_own=bool(row["is_own"])) for row in rows]

    def errors(self):
        return [dict(row) for row in self.conn.execute("SELECT * FROM import_errors ORDER BY id")]

    def captures(self, url):
        link = self._link(url)
        self._topic(link)
        return [dict(row) for row in self.conn.execute("""SELECT capture_id,captured_at,kind,origin,
            source_hash,new_count,edit_count FROM captures WHERE host=? AND topic_id=? ORDER BY id""",
                                                       (link.host, link.topic_id))]

    def _record_error(self, error, link=None, capture_id=None):
        try:
            with self.transaction():
                saved = self.conn.execute("""INSERT INTO import_errors(recorded_at,host,topic_id,capture_id,
                    code,message,details_json) VALUES (?,?,?,?,?,?,?)""",
                                  (now(), link.host if link else None, link.topic_id if link else None,
                                   capture_id, error.code, str(error), json_text(error.details)))
            error.details["recorded_error_id"] = saved.lastrowid
        except sqlite3.Error as exc:
            raise WatchError("ERROR_LOG_FAILED", "Import failed; the separate error record could not be persisted.",
                             {"original_code": error.code}) from exc

    def import_file(self, url, path):
        require(self.storage_mode == "SYNTHETIC_ONLY", "ORIGIN_MISMATCH", "Real storage does not accept JSON file imports.")
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            error = WatchError("CAPTURE_READ_FAILED", "Could not read a UTF-8 synthetic capture file.")
            self._record_error(error)
            raise error from exc
        try:
            value = load_json(raw)
        except WatchError as error:
            self._record_error(error)
            raise
        return self.import_capture(url, value)

    def import_capture(self, url, value):
        link = None
        capture = None
        try:
            link = self._link(url)
            require(self.storage_mode == "SYNTHETIC_ONLY", "ORIGIN_MISMATCH", "Real storage accepts only a fresh browser read.")
            capture = Capture.parse(value)
            require((capture.host, capture.topic_id) == (link.host, link.topic_id),
                    "TOPIC_MISMATCH", "Capture does not belong to the requested topic.")
            with self.transaction():
                return self._accept_capture(link, capture)
        except WatchError as error:
            self._record_error(error, link, capture.capture_id if capture else None)
            raise
        except sqlite3.Error as exc:
            error = WatchError("TRANSACTION_FAILED", "Import transaction failed and was rolled back.",
                               {"sqlite_error": getattr(exc, "sqlite_errorname", "SQLITE_ERROR")})
            self._record_error(error, link, capture.capture_id if capture else None)
            raise error from exc

    def _accept_capture(self, link, capture):
        expected_origin = "AUTHENTICATED_FORUM" if self.storage_mode == REAL_STORAGE_MODE else "SYNTHETIC"
        require(capture.origin == expected_origin, "ORIGIN_MISMATCH", "Capture and storage origins differ.")
        key = (link.host, link.topic_id)
        topic = self._topic(link)
        previous = self.conn.execute("SELECT * FROM captures WHERE host=? AND topic_id=? AND capture_id=?",
                                     (*key, capture.capture_id)).fetchone()
        if previous:
            require(previous["source_hash"] == capture.source_hash, "CAPTURE_ID_CONFLICT",
                    "Capture ID already exists with different data; previous capture was preserved.")
            return {"result": "REPLAY", "capture_id": capture.capture_id,
                    "new_changes": 0, "edit_changes": 0, "state_advanced": False}
        require(topic["state"] != "CLOSED", "TOPIC_CLOSED", "Closed topics reject new imports.")
        latest = self.conn.execute("SELECT * FROM captures WHERE id=?", (topic["last_capture_pk"],)).fetchone()
        if latest:
            require(capture.captured_at > latest["captured_at"], "OUT_OF_ORDER_CAPTURE",
                    "A new capture ID must have a later observation time than the last valid capture.")
        known = {row["message_id"]: row for row in self.conn.execute("""SELECT m.*,r.content_hash
            FROM messages m JOIN revisions r ON r.host=m.host AND r.topic_id=m.topic_id
            AND r.message_id=m.message_id AND r.revision=m.current_revision
            WHERE m.host=? AND m.topic_id=?""", key)}
        incoming_ids = [message.message_id for message in capture.messages]
        missing = sorted(known.keys() - set(incoming_ids))
        if missing:
            raise WatchError("MISSING_MESSAGES", "Known messages disappeared; capture was not accepted.",
                             {"missing_message_ids": missing})
        if latest:
            previous_order = [row[0] for row in self.conn.execute(
                "SELECT message_id FROM capture_messages WHERE capture_pk=? ORDER BY ordinal", (latest["id"],))]
            require([item for item in incoming_ids if item in known] == previous_order,
                    "MESSAGE_ORDER_CHANGED", "Previously observed message order changed unexpectedly.")
        for message in capture.messages:
            require(message.message_id not in known or known[message.message_id]["author_id"] == message.author_id,
                    "AUTHOR_CHANGED", "A known message changed author; manual investigation is required.")
        baseline = latest is None
        cursor = self.conn.execute("""INSERT INTO captures(host,topic_id,capture_id,captured_at,imported_at,
            origin,complete,kind,source_hash,source_json,new_count,edit_count)
            VALUES (?,?,?,?,?,?,1,?,?,?,0,0)""",
                                   (*key, capture.capture_id, capture.captured_at, now(),
                                    capture.origin, "BASELINE" if baseline else "UPDATE", capture.source_hash, capture.source_json))
        capture_pk = cursor.lastrowid
        counts = {"NEW_MESSAGE": 0, "CONTENT_EDIT": 0}
        for ordinal, message in enumerate(capture.messages):
            old = known.get(message.message_id)
            changed = old is None or old["content_hash"] != message.content_hash
            revision = (old["current_revision"] + int(changed)) if old else 1
            if old is None:
                self.conn.execute("INSERT INTO messages VALUES (?,?,?,?,?)",
                                  (*key, message.message_id, message.author_id, revision))
            elif changed:
                self.conn.execute("UPDATE messages SET current_revision=? WHERE host=? AND topic_id=? AND message_id=?",
                                  (revision, *key, message.message_id))
            if changed:
                self.conn.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)",
                                  (*key, message.message_id, revision, capture_pk, message.content,
                                   message.normalized_content, message.content_hash))
                if not baseline:
                    kind = "NEW_MESSAGE" if old is None else "CONTENT_EDIT"
                    self.conn.execute("""INSERT INTO pending_changes(host,topic_id,capture_pk,ordinal,
                        message_id,revision,kind,is_own,state) VALUES (?,?,?,?,?,?,?,?,'PENDING_EVALUATION')""",
                                      (*key, capture_pk, ordinal, message.message_id, revision, kind,
                                       int(message.author_id == self.settings.expected_account_id)))
                    counts[kind] += 1
            self.conn.execute("INSERT INTO capture_messages VALUES (?,?,?,?,?,?,?)",
                              (capture_pk, ordinal, *key, message.message_id, revision, message.metadata_json))
        self.conn.execute("UPDATE captures SET new_count=?,edit_count=? WHERE id=?",
                          (counts["NEW_MESSAGE"], counts["CONTENT_EDIT"], capture_pk))
        self.conn.execute("UPDATE topics SET last_capture_pk=? WHERE host=? AND topic_id=?", (capture_pk, *key))
        from .drafts import invalidate
        invalidate(self, link)
        return {"result": "BASELINE" if baseline else ("CHANGES" if sum(counts.values()) else "NO_RELEVANT_CHANGES"),
                "capture_id": capture.capture_id, "new_changes": counts["NEW_MESSAGE"],
                "edit_changes": counts["CONTENT_EDIT"], "state_advanced": True}

    def read_once(self, profile, *, max_pages=20, time_budget_seconds=180):
        """The only public entry to real import performs its own fresh live read."""
        from .adapter import FIRST_PAGE
        from .reader import collect_live
        require(self.storage_mode == REAL_STORAGE_MODE, "ORIGIN_MISMATCH", "Live reads require separate authenticated storage.")
        link = self._link(FIRST_PAGE)
        try:
            require(self._topic(link)["state"] != "CLOSED", "TOPIC_CLOSED", "Closed topics reject manual reads.")
            capture = collect_live(profile, max_pages=max_pages, time_budget_seconds=time_budget_seconds)
            with self.transaction():
                result = self._accept_capture(link, capture)
            metadata = load_json(capture.source_json)["metadata"]
            return dict(result, origin=capture.origin, pages_read=len(metadata["pages_visited"]),
                        messages_read=len(capture.messages), last_observed_message_id=capture.messages[-1].message_id,
                        page_observations=metadata["page_observations"], attempts=metadata["attempts"],
                        session_identity_status="VERIFIED_FOR_THIS_EXECUTION", observed_account_id=59,
                        observed_at=capture.captured_at, topic_state=self._topic(link)["state"],
                        last_processed_message_id=self._topic(link)["last_processed_message_id"])
        except WatchError as error:
            self._record_error(error, link)
            raise
        except sqlite3.Error as exc:
            error = WatchError("TRANSACTION_FAILED", "Real import transaction failed and was rolled back.",
                               {"sqlite_error": getattr(exc, "sqlite_errorname", "SQLITE_ERROR")})
            self._record_error(error, link)
            raise error from exc
