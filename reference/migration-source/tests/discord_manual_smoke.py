"""Two explicitly staged Discord sends in a separate SYNTHETIC workflow database."""

from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forum_watch import notifications
from forum_watch.models import HOST, INITIAL_URL, WatchError, require
from forum_watch.narrative import evaluate
from forum_watch.store import Store, WORKSPACE


class SyntheticInterpreter:
    """Fixed test result, no model call or narrator credentials."""
    def generate(self, package):
        return {"decision": "DRAFT_READY", "reason": "PRUEBA / DATOS SINTÉTICOS",
                "important_decisions": [], "ic_facts_used": ["assessment:a1"], "uncertainties": [],
                "scene_assessment": [{"ref": "a1", "source_ref": "message:discord-test-s2:r1",
                                     "kind": "OBSERVABLE_IC", "summary": "Pregunta social sintética."}],
                "draft": "Me detuve a escuchar. —[color=#87CEEB]Me gustaría saber qué estás leyendo.[/color]",
                "memory_candidates": []}


def prepare_pipeline(store):
    require(not store.conn.execute("SELECT 1 FROM captures").fetchone(), "DEMO_ALREADY_STARTED",
            "Synthetic workflow already exists; use the existing queued event instead of recreating it.")
    messages = [{"message_id": "discord-test-s1", "author_id": 59, "content": "BASELINE EXCLUSIVAMENTE SINTÉTICO"}]
    for number in (1, 2):
        if number == 2:
            messages.append({"message_id": "discord-test-s2", "author_id": 7001,
                             "content": "—¿Qué te gusta leer? [PRUEBA SINTÉTICA]",
                             "metadata": {"author_name_observed": "Interlocutor sintético"}})
        store.import_capture(INITIAL_URL, {
            "schema_version": 1, "origin": "SYNTHETIC", "capture_id": f"discord-pipeline-{number}",
            "captured_at": f"2026-09-13T15:0{number}:00+00:00", "complete": True,
            "topic": {"host": HOST, "topic_id": 275}, "messages": deepcopy(messages),
            "metadata": {"title_observed": "PRUEBA / DATOS SINTÉTICOS — aviso de borrador"}})
    result = evaluate(store, INITIAL_URL, SyntheticInterpreter())
    require(result["decision"] == "DRAFT_READY", "DEMO_GENERATION_FAILED", "Synthetic evaluation did not produce a draft.")
    notifications.collect(store)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, help="Separate operational directory outside the character tree.")
    parser.add_argument("--stage", choices=["connection", "pipeline"], required=True)
    parser.add_argument("--prepare-only", action="store_true", help="Queue and preview the fixed message, without reading the secret or sending.")
    args = parser.parse_args()
    folder = Path(args.output_root).resolve()
    require(not folder.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Demo data must be outside the character tree.")
    db = folder / "discord-synthetic.sqlite3"
    if args.stage == "connection" and not folder.exists():
        folder.mkdir(parents=True)
    require(folder.is_dir(), "DEMO_NOT_FOUND", "Prepare the connection stage first.")
    with Store(db, create=args.stage == "connection") as store:
        store.add(INITIAL_URL)
        if args.stage == "connection":
            notifications.connection_test(store)
        else:
            notifications.initialize(store)
            require(store.conn.execute("SELECT 1 FROM notifications WHERE type='CONNECTION_TEST' AND status='SENT'").fetchone(),
                    "CONNECTION_TEST_NOT_CONFIRMED", "First confirm the controlled connection test.")
            if not store.conn.execute("SELECT 1 FROM captures").fetchone():
                prepare_pipeline(store)
            else:
                notifications.collect(store)
        # A repeated connection command must not accidentally send a queued
        # pipeline event, and this demo must not drain unrelated events.
        expected = "CONNECTION_TEST" if args.stage == "connection" else "DRAFT_READY"
        queued = notifications.list_notifications(store, preview=True)
        require(all(row["type"] in {"CONNECTION_TEST", "DRAFT_READY"} for row in queued),
                "UNEXPECTED_DEMO_EVENT", "Demo contains unexpected events; no send attempted.")
        if args.prepare_only:
            report = {"result": "PREPARED_WITHOUT_SEND", "stage": args.stage,
                      "notifications": [r for r in queued if r["type"] == expected]}
        elif any(r["type"] == expected and r["status"] == "SENT" for r in queued):
            report = {"result": "ALREADY_SENT", "stage": args.stage,
                      "notifications": [r for r in queued if r["type"] == expected], "attempted": 0}
        else:
            require(all(r["type"] == expected or r["status"] == "SENT" for r in queued),
                    "UNEXPECTED_DEMO_EVENT", "Another event is pending; no send attempted.")
            report = notifications.send_pending(store, limit=1)
            report["stage"] = args.stage
        report["origin"] = "SYNTHETIC"
        report["forum_read_performed"] = False
        report["model_invoked"] = False
        (folder / (args.stage + ("-preview.json" if args.prepare_only else "-report.json"))).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
        if args.prepare_only:
            return 0
        return 0 if any(r["status"] == "SENT" for r in report.get("notifications", [])) else 2

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchError as error:
        print(json.dumps({"error": error.code, "message": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
    except (OSError, ValueError):
        print('{"error":"LOCAL_DEMO_FAILURE","secret_displayed":false}')
        raise SystemExit(3)

