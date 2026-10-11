"""Task Scheduler entry point. Absolute source import; no UI or resident loop."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forum_watch.models import WatchError
from forum_watch.workflow import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-config", required=True)
    parser.add_argument("--trigger", choices=["MANUAL", "SCHEDULED"], default="SCHEDULED")
    args = parser.parse_args()
    try:
        result = run_once(args.workflow_config, trigger=args.trigger)
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=True))
        return 0 if result["status"] in {"COMPLETED", "SKIPPED_LOCKED"} else 2
    except Exception as error:
        if sys.stderr is not None:
            print(json.dumps({"error": error.code if isinstance(error, WatchError) else "WORKFLOW_START_FAILED"}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

