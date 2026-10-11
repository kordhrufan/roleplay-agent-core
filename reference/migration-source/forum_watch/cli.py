"""One-shot commands. Browser login and isolated model evaluation are explicit."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .models import WatchError, load_json, parse_config
from .store import Store


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # A mistakenly pasted webhook must not be echoed by argparse either.
        if "webhook" in message.lower():
            message = "Invalid arguments; configure the webhook only through hidden local input."
        super().error(message)


def parser():
    root = SafeArgumentParser(description="Forum Watch: manual ingestion, isolated narrative evaluation and Discord notices.")
    root.add_argument("--db", help="Explicit SQLite path; required for storage commands.")
    root.add_argument("--workflow-config", help="Absolute external workflow JSON; defaults to the local operational configuration.")
    root.add_argument("--storage-mode", choices=["SYNTHETIC_ONLY", "AUTHENTICATED_ONLY"], default="SYNTHETIC_ONLY")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Local topic, outbox and run status; no network or session verification.")
    cycle = sub.add_parser("run-once", help="One bounded workflow cycle; ACTIVE topics only.")
    cycle.add_argument("--trigger", choices=["MANUAL", "SCHEDULED"], default="MANUAL")
    topic = sub.add_parser("topic").add_subparsers(dest="topic_command", required=True)
    topic.add_parser("list")
    for action in ("add", "inspect", "pause", "resume", "close"):
        topic.add_parser(action).add_argument("topic")
    draft = sub.add_parser("draft").add_subparsers(dest="draft_command", required=True)
    draft.add_parser("list").add_argument("topic", nargs="?", default="275")
    draft.add_parser("inspect").add_argument("draft_id")
    scheduler = sub.add_parser("scheduler").add_subparsers(dest="scheduler_command", required=True)
    for action in ("status", "prepare", "disable", "enable", "remove", "run"):
        scheduler.add_parser(action)
    install = scheduler.add_parser("install")
    install.add_argument("--plan", required=True)
    install.add_argument("--approved-plan-sha256", required=True)
    sub.add_parser("configure-discord", help="Hidden local terminal input; encrypt webhook with current-user Windows DPAPI; sends nothing.")
    sub.add_parser("queue-notifications", help="Project persisted workflow events into the outbox; no Discord connection.")
    sub.add_parser("queue-discord-test", help="Queue the fixed connection test in a separate synthetic DB; sends nothing.")
    notices = sub.add_parser("notifications", help="Inspect local notification status; no webhook access.")
    notices.add_argument("view", nargs="?", choices=["pending"])
    notices.add_argument("--preview", action="store_true", help="Show the compact outgoing payload without secrets.")
    notify = sub.add_parser("notify", help="Send one bounded manual batch of eligible notifications to Discord.")
    notify.add_argument("--limit", type=int, default=10)
    retry = sub.add_parser("retry-notification", help="Explicitly retry a corrected, definite configuration failure; never an uncertain delivery.")
    retry.add_argument("notification_id")
    login = sub.add_parser("login", help="Open dedicated Edge for manual login; never extracts or imports messages.")
    login.add_argument("--profile", required=True)
    login.add_argument("--timeout-seconds", type=int, default=600)
    read = sub.add_parser("read-once", help="One authenticated read of topic 275; preserves PAUSED and never schedules work.")
    read.add_argument("--profile", required=True)
    read.add_argument("--max-pages", type=int, default=20)
    read.add_argument("--time-budget-seconds", type=int, default=180)
    for command in ("evaluate", "evaluations", "drafts"):
        child = sub.add_parser(command, help="Manual isolated narrative operation; never reads the forum.")
        child.add_argument("url")
    retire = sub.add_parser("retire-draft", help="Retire a pending draft explicitly, preserving its file and history; does not approve it.")
    retire.add_argument("url")
    retire.add_argument("draft_id")
    init = sub.add_parser("init", help="Explicitly initialize the example topic in PAUSED state.")
    init.add_argument("--config", required=True)
    for command in ("add", "inspect", "pause", "resume", "close", "pending", "captures"):
        child = sub.add_parser(command)
        child.add_argument("url")
    sub.add_parser("list")
    sub.add_parser("errors")
    versions = sub.add_parser("versions")
    versions.add_argument("url")
    versions.add_argument("--message-id")
    capture = sub.add_parser("import", help="Import an explicit complete synthetic snapshot, including while PAUSED.")
    capture.add_argument("url")
    capture.add_argument("capture_file")
    return root


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    operational = {"status", "run-once", "scheduler", "topic", "draft", "notifications"}
    if args.command not in {"login", "configure-discord"} | operational and not args.db:
        root.error("--db is required for storage commands")
    try:
        if args.command in {"status", "run-once", "scheduler"}:
            if args.command == "scheduler":
                from . import scheduler
                if args.scheduler_command == "prepare":
                    result = scheduler.prepare(args.workflow_config)
                elif args.scheduler_command == "install":
                    result = scheduler.install(args.plan, args.approved_plan_sha256)
                else:
                    result = scheduler.bridge(args.scheduler_command.capitalize())
            else:
                from . import workflow
                result = (workflow.status(args.workflow_config) if args.command == "status"
                          else workflow.run_once(args.workflow_config, trigger=args.trigger))
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2 if args.command == "run-once" and result["status"] not in {"COMPLETED", "SKIPPED_LOCKED"} else 0
        if args.command in {"topic", "draft", "notifications"} and not args.db:
            from .workflow_config import load
            config = load(args.workflow_config)
            args.db, args.storage_mode = config["database"], config["storage_mode"]
        if args.command == "configure-discord":
            from .discord_secret import configure
            print(json.dumps(configure(), ensure_ascii=True, indent=2))
            return 0
        if args.command == "login":
            from .browser import manual_login
            result = manual_login(args.profile, timeout_seconds=args.timeout_seconds)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        settings = None
        initial = None
        if args.command == "init":
            settings, initial = parse_config(load_json(Path(args.config).read_text(encoding="utf-8")))
        with Store(args.db, settings, create=args.command in {"init", "add"}, storage_mode=args.storage_mode) as store:
            if args.command == "topic":
                from .models import HOST
                if args.topic_command == "list":
                    result = store.list_topics()
                else:
                    url = f"https://{HOST}/index.php?showtopic={int(args.topic)}" if args.topic.isdecimal() else args.topic
                    if args.topic_command in {"pause", "resume", "close"}:
                        result = store.set_state(url, {"pause": "PAUSED", "resume": "ACTIVE", "close": "CLOSED"}[args.topic_command])
                    else:
                        result = getattr(store, args.topic_command)(url)
            elif args.command == "draft":
                from . import drafts
                from .models import HOST, require
                if args.draft_command == "list":
                    url = f"https://{HOST}/index.php?showtopic={int(args.topic)}" if args.topic.isdecimal() else args.topic
                    result = drafts.list_drafts(store, url)
                else:
                    drafts.initialize(store)
                    row = store.conn.execute("SELECT host,topic_id FROM narrative_drafts WHERE id=?", (args.draft_id,)).fetchone()
                    require(row is not None, "DRAFT_NOT_FOUND", "No such operational draft.")
                    rows = drafts.list_drafts(store, f"https://{row['host']}/index.php?showtopic={row['topic_id']}")
                    result = next(r for r in rows if r["id"] == args.draft_id)
                    result["text"] = Path(result["file_path"]).read_text(encoding="utf-8") if Path(result["file_path"]).is_file() else None
            elif args.command in {"queue-notifications", "notifications", "queue-discord-test", "notify", "retry-notification"}:
                from . import notifications
                if args.command == "queue-notifications":
                    result = notifications.collect(store)
                elif args.command == "notifications":
                    result = notifications.list_notifications(store, preview=args.preview)
                    if args.view == "pending":
                        result = [r for r in result if r["status"] in {"PENDING", "FAILED_RETRYABLE", "SENDING"}]
                elif args.command == "queue-discord-test":
                    result = notifications.connection_test(store)
                elif args.command == "retry-notification":
                    result = notifications.retry_configuration_failure(store, args.notification_id)
                else:
                    result = notifications.send_pending(store, limit=args.limit)
            elif args.command == "init":
                result = store.add(initial.original_url)
            elif args.command == "add":
                result = store.add(args.url)
            elif args.command == "list":
                result = store.list_topics()
            elif args.command == "inspect":
                result = store.inspect(args.url)
            elif args.command in {"pause", "resume", "close"}:
                result = store.set_state(args.url, {"pause": "PAUSED", "resume": "ACTIVE", "close": "CLOSED"}[args.command])
            elif args.command == "import":
                result = store.import_file(args.url, args.capture_file)
            elif args.command == "versions":
                result = store.versions(args.url, args.message_id)
            elif args.command == "pending":
                result = store.pending(args.url)
            elif args.command == "captures":
                result = store.captures(args.url)
            elif args.command == "read-once":
                result = store.read_once(args.profile, max_pages=args.max_pages, time_budget_seconds=args.time_budget_seconds)
            elif args.command == "evaluate":
                from .narrative import evaluate
                result = evaluate(store, args.url)
            elif args.command == "evaluations":
                from .narrative import evaluations
                result = evaluations(store, args.url)
            elif args.command == "drafts":
                from .drafts import list_drafts
                result = list_drafts(store, args.url)
            elif args.command == "retire-draft":
                from .drafts import retire
                result = retire(store, args.url, args.draft_id)
            else:
                result = store.errors()
        print(json.dumps({"storage_mode": args.storage_mode, "data": result}, ensure_ascii=True, indent=2))
        failed = (args.command == "evaluate" and result["decision"] == "GENERATION_FAILED") or (
            args.command == "notify" and any(r["status"].startswith("FAILED") for r in result["notifications"]))
        return 2 if failed else 0
    except WatchError as exc:
        print(json.dumps({"error": exc.code, "message": str(exc), "details": exc.details}, ensure_ascii=True), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"error": "LOCAL_FAILURE", "message": "Local I/O or database operation failed.",
                          "exception_type": type(exc).__name__}), file=sys.stderr)
        return 3
