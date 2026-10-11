"""Explicit local workflow configuration, never derived from forum content."""

import os
from pathlib import Path

from .models import digest, json_text, load_json, require
from .store import WORKSPACE

INTERVAL = 14400


def operational_root():
    require(bool(os.environ.get("LOCALAPPDATA")), "OPERATIONAL_ROOT_UNAVAILABLE", "LOCALAPPDATA is required.")
    path = (Path(os.environ["LOCALAPPDATA"]) / "NozomuForumWatch").resolve()
    require(not path.is_relative_to(WORKSPACE.parent), "PROTECTED_PATH", "Operational state must be outside the character tree.")
    return path


def default_path():
    return operational_root() / "workflow-config.json"


def load(path=None):
    path = Path(path) if path is not None else default_path()
    require(path.is_absolute() and path.is_file() and not path.resolve().is_relative_to(WORKSPACE.parent),
            "INVALID_WORKFLOW_CONFIG", "Use an existing absolute operational configuration outside the character tree.")
    require(path.stat().st_size <= 16000, "INVALID_WORKFLOW_CONFIG", "Workflow configuration exceeds its size budget.")
    value = load_json(path.read_text(encoding="utf-8"))
    fields = {"schema_version", "storage_mode", "database", "browser_profile", "python_executable", "codex_executable",
              "interval_seconds", "generation_timeout_seconds", "read_timeout_seconds", "max_pages", "notification_limit"}
    require(isinstance(value, dict) and set(value) == fields, "INVALID_WORKFLOW_CONFIG", "Unknown or missing configuration fields.")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["storage_mode"] in {"AUTHENTICATED_ONLY", "SYNTHETIC_ONLY"}
            and type(value["interval_seconds"]) is int and value["interval_seconds"] == INTERVAL
            and type(value["generation_timeout_seconds"]) is int and value["generation_timeout_seconds"] == 300,
            "INVALID_WORKFLOW_CONFIG", "Expected schema 1, four-hour interval and five-minute generation budget.")
    for field, low, high in (("read_timeout_seconds", 1, 300), ("max_pages", 1, 20), ("notification_limit", 1, 20)):
        require(type(value[field]) is int and low <= value[field] <= high, "INVALID_WORKFLOW_CONFIG", "Invalid bounded workflow limit.")
    for field in ("database", "browser_profile", "python_executable", "codex_executable"):
        require(isinstance(value[field], str) and Path(value[field]).is_absolute(),
                "INVALID_WORKFLOW_CONFIG", "Configured paths must be absolute.")
        value[field] = str(Path(value[field]).resolve())
    require(Path(value["database"]).is_file() and not Path(value["database"]).is_relative_to(WORKSPACE.parent),
            "INVALID_WORKFLOW_CONFIG", "Workflow requires an existing external database; it never rebuilds one.")
    require(not Path(value["browser_profile"]).is_relative_to(WORKSPACE.parent),
            "PROTECTED_PATH", "The dedicated browser profile must be external.")
    if value["storage_mode"] == "AUTHENTICATED_ONLY":
        require(Path(value["browser_profile"]).is_dir(), "BROWSER_PROFILE_MISSING", "Restore the dedicated profile manually.")
        require(Path(value["python_executable"]) == (WORKSPACE / ".venv-forum-watch/Scripts/python.exe").resolve()
                and Path(value["python_executable"]).is_file(), "WRONG_WORKFLOW_PYTHON", "Use the verified reader virtual environment.")
        require(Path(value["codex_executable"]).is_file(), "CODEX_NOT_FOUND", "Configured native Codex executable is missing.")
    value["config_path"] = str(path.resolve())
    value["config_hash"] = digest(json_text({k: value[k] for k in sorted(fields)}))
    return value

