"""Reviewable Windows Task Scheduler plan. Registration requires its explicit approval hash."""

from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from .models import WatchError, load_json, require
from .store import WORKSPACE
from .workflow_config import load, operational_root

TASK_NAME = "NozomuForumWatch"
MARKER = "NozomuForumWatch Hito5 managed"
SCRIPT = WORKSPACE / "scripts/manage-forum-watch-scheduler.ps1"
BOOTSTRAP = WORKSPACE / "scripts/run-forum-watch.py"
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def bridge(action, *, plan=None, approved_hash=None):
    require(os.name == "nt", "WINDOWS_SCHEDULER_REQUIRED", "Windows Task Scheduler is required.")
    shell = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    require(shell.is_file() and SCRIPT.is_file(), "SCHEDULER_TOOL_MISSING", "Verified PowerShell bridge is missing.")
    args = [str(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Action", action]
    if plan:
        args += ["-PlanPath", str(Path(plan).resolve())]
    if approved_hash:
        args += ["-ApprovedPlanSha256", approved_hash]
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8-sig", timeout=45, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WatchError("SCHEDULER_BRIDGE_FAILED", "Scheduler process did not complete; inspect task status before retrying a mutation.") from error
    try:
        value = load_json(result.stdout.strip())
    except Exception:
        require(False, "SCHEDULER_BRIDGE_FAILED", "Scheduler bridge failed; raw process output is not exposed.")
    require(result.returncode == 0 and not value.get("error"), value.get("error", "SCHEDULER_BRIDGE_FAILED"),
            "Scheduler operation was not completed; inspect its safe status/error code.")
    return value


def task_xml(config, sid, start_at):
    root = ET.Element("Task", {"xmlns": NS, "version": "1.2"})
    def child(parent, tag, text=None, **attributes):
        element = ET.SubElement(parent, tag, attributes)
        if text is not None:
            element.text = str(text)
        return element
    info = child(root, "RegistrationInfo")
    child(info, "Description", MARKER + "; config=" + config["config_hash"])
    child(info, "URI", "\\" + TASK_NAME)
    trigger = child(child(root, "Triggers"), "TimeTrigger")
    repetition = child(trigger, "Repetition")
    child(repetition, "Interval", "PT4H")
    child(repetition, "StopAtDurationEnd", "false")
    child(trigger, "StartBoundary", start_at)
    child(trigger, "Enabled", "true")
    principal = child(child(root, "Principals"), "Principal", id="Author")
    child(principal, "UserId", sid)
    child(principal, "LogonType", "InteractiveToken")
    child(principal, "RunLevel", "LeastPrivilege")
    settings = child(root, "Settings")
    for key, value in {
        "MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
        "StopIfGoingOnBatteries": "false", "AllowHardTerminate": "true",
        "StartWhenAvailable": "true", "RunOnlyIfNetworkAvailable": "false",
        "AllowStartOnDemand": "true", "Enabled": "true", "Hidden": "false",
        "WakeToRun": "false", "ExecutionTimeLimit": "PT30M", "Priority": "7",
    }.items():
        child(settings, key, value)
    action = child(child(root, "Actions", Context="Author"), "Exec")
    pythonw = str(Path(config["python_executable"]).with_name("pythonw.exe"))
    arguments = subprocess.list2cmdline(["-B", str(BOOTSTRAP), "--workflow-config", config["config_path"], "--trigger", "SCHEDULED"])
    child(action, "Command", pythonw)
    child(action, "Arguments", arguments)
    child(action, "WorkingDirectory", str(Path(config["config_path"]).parent))
    return ET.tostring(root, encoding="unicode"), pythonw, arguments


def prepare(config_path=None, *, root=None, identity=None, start_at=None):
    config = load(config_path)
    require(config["storage_mode"] == "AUTHENTICATED_ONLY", "SYNTHETIC_SCHEDULER_FORBIDDEN", "Only the existing authenticated workflow may be scheduled.")
    root = Path(root) if root is not None else operational_root()
    require(not root.resolve().is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Scheduler plan must be operational.")
    identity = identity or bridge("Status")
    sid = identity["current_user_sid"]
    require(isinstance(sid, str) and sid.startswith("S-1-5-"), "INVALID_TASK_IDENTITY", "Current Windows user SID is required.")
    start_at = start_at or (datetime.now().astimezone() + timedelta(hours=4)).isoformat(timespec="seconds")
    require(datetime.fromisoformat(start_at).utcoffset() is not None, "INVALID_TASK_START", "Task start must include a timezone.")
    xml, pythonw, arguments = task_xml(config, sid, start_at)
    require(Path(pythonw).is_file() and BOOTSTRAP.is_file(), "SCHEDULER_TOOL_MISSING", "Virtual-environment pythonw or bootstrap is missing.")
    plan = {"schema_version": 1, "task_name": TASK_NAME, "description_marker": MARKER,
            "config_path": config["config_path"], "config_hash": config["config_hash"],
            "config_file_sha256": hashlib.sha256(Path(config["config_path"]).read_bytes()).hexdigest(),
            "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest(),
            "current_user_sid": sid, "current_user_name": identity.get("current_user_name"),
            "execute": pythonw, "arguments": arguments, "working_directory": str(Path(config["config_path"]).parent),
            "interval_seconds": 14400, "start_at": start_at, "multiple_instances": "IgnoreNew",
            "start_when_available": True, "wake_to_run": False, "logon_type": "InteractiveToken",
            "run_level": "LeastPrivilege", "execution_time_limit": "PT30M", "xml": xml}
    raw = json.dumps(plan, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("scheduler-plan-" + hashed[:16] + ".json")
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(raw)
    else:
        require(path.read_bytes() == raw.encode("utf-8"), "PLAN_COLLISION", "Existing plan differs; nothing was overwritten.")
    return {"result": "SCHEDULER_PREPARED_NOT_INSTALLED", "plan_path": str(path), "plan_sha256": hashed,
            "existing_task": identity.get("task_exists"), "configuration": {k: v for k, v in plan.items() if k != "xml"}}


def install(plan_path, approved_hash):
    require(plan_path and approved_hash, "SCHEDULER_APPROVAL_REQUIRED", "Review the final plan and explicitly approve its SHA-256 before registration.")
    path = Path(plan_path)
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == approved_hash,
            "SCHEDULER_PLAN_CHANGED", "Approved plan differs; nothing was registered.")
    plan = load_json(path.read_text(encoding="utf-8"))
    config = load(plan["config_path"])
    require(config["config_hash"] == plan["config_hash"]
            and hashlib.sha256(Path(config["config_path"]).read_bytes()).hexdigest() == plan["config_file_sha256"]
            and hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest() == plan["bootstrap_sha256"],
            "SCHEDULER_PLAN_CHANGED", "Configuration or bootstrap changed after review.")
    return bridge("Install", plan=path, approved_hash=approved_hash)
