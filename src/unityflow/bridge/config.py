import json
import os
from pathlib import Path

UNITY_BRIDGE_HOST = os.environ.get("UNITY_BRIDGE_HOST", "localhost")
UNITY_BRIDGE_TIMEOUT = int(os.environ.get("UNITY_BRIDGE_TIMEOUT", "30"))

_DEFAULT_PORT = 29184
_REGISTRY_PATH = Path.home() / ".unityflow" / "instances.json"


def _discover_port_for_project(working_dir: str) -> int | None:
    if not _REGISTRY_PATH.exists():
        return None

    try:
        entries = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(entries, list):
        return None

    working = Path(working_dir).resolve().as_posix().lower()

    for entry in entries:
        project = entry.get("projectPath", "")
        if not project:
            continue
        project_lower = project.lower()
        if working.startswith(project_lower) or project_lower.startswith(working):
            return entry.get("port")

    return None


def get_port() -> int:
    explicit = os.environ.get("UNITY_BRIDGE_PORT")
    if explicit:
        return int(explicit)

    discovered = _discover_port_for_project(os.getcwd())
    if discovered:
        return discovered

    return _DEFAULT_PORT


def base_url():
    return f"http://{UNITY_BRIDGE_HOST}:{get_port()}"
