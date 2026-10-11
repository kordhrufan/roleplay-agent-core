"""Small independent run journal and OS lock, shared by manual/scheduled/recovery runs."""

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import sys

from .models import json_text, load_json, require
from .store import now

COUNTERS = ("topics_considered", "topics_read", "changes_detected", "jobs_evaluated",
            "drafts_created", "notifications_created", "notifications_sent")
APP_ID = 0x46575235


def error_code(error):
    code = getattr(error, "code", type(error).__name__.upper())
    return code if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code) else "UNEXPECTED_ERROR"


@contextmanager
def cycle_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "workflow.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        acquired = False
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                handle.seek(0)
                if sys.platform == "win32":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Audit:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(root / "workflow-runs.sqlite3", timeout=5, isolation_level=None)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not names:
                require(self.conn.execute("PRAGMA application_id").fetchone()[0] == 0,
                        "RUN_JOURNAL_MISMATCH", "Refusing an unrelated journal database.")
                self.conn.execute("CREATE TABLE runs(run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, trigger TEXT NOT NULL, status TEXT NOT NULL, data_json TEXT NOT NULL)")
                self.conn.execute(f"PRAGMA application_id={APP_ID}")
                self.conn.execute("PRAGMA user_version=1")
            require(names in (set(), {"runs"}) and self.conn.execute("PRAGMA application_id").fetchone()[0] == APP_ID
                    and self.conn.execute("PRAGMA user_version").fetchone()[0] == 1,
                    "RUN_JOURNAL_MISMATCH", "Unsupported run journal.")
            self.conn.execute("COMMIT")
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def save(self, run):
        self.conn.execute("""INSERT INTO runs VALUES(?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET finished_at=excluded.finished_at,
            status=excluded.status,data_json=excluded.data_json""",
            (run["run_id"], run["started_at"], run["finished_at"], run["trigger"], run["status"], json_text(run)))

    def recover(self):
        for row in self.conn.execute("SELECT data_json FROM runs WHERE status='RUNNING'").fetchall():
            run = load_json(row[0])
            run["status"], run["finished_at"] = "INTERRUPTED", now()
            run["error_summary"].append({"phase": "RECOVERY", "code": "INTERRUPTED_EXECUTION"})
            self.save(run)

    def latest(self, limit=20):
        return [load_json(r[0]) for r in self.conn.execute("SELECT data_json FROM runs ORDER BY started_at DESC,run_id DESC LIMIT ?", (limit,))]

