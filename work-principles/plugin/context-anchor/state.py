"""State management for context-anchor plugin.
Reads/writes ~/.hermes/persistent/state.json via shell command.
Hermes kernel restores persistent/ content across sessions automatically."""

import json
import os
import subprocess
from pathlib import Path

PERSISTENT_DIR = Path(os.environ.get("HOME", "~/.hermes")) / ".hermes" / "persistent"
STATE_FILE = PERSISTENT_DIR / "state.json"


def _ensure_persistent_dir() -> Path:
    PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)
    return PERSISTENT_DIR


def _read_state_raw() -> dict:
    _ensure_persistent_dir()
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Auto-detect hostname on first run
        host = "localhost"
        try:
            import subprocess
            host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=5).stdout.strip() or "localhost"
        except Exception:
            pass
        return {"current_host": host, "current_task": "awaiting-user-input", "updated_at": None, "thread_session_ids": []}


def _write_state(state: dict):
    _ensure_persistent_dir()
    state["updated_at"] = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True, text=True
    ).stdout.strip()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_state() -> dict:
    return _read_state_raw()


def set_host(host: str):
    state = _read_state_raw()
    state["current_host"] = host
    _write_state(state)


def set_task(task: str):
    state = _read_state_raw()
    state["current_task"] = task
    _write_state(state)


def record_session(session_id: str):
    """Append session_id to thread history (deduped)."""
    state = _read_state_raw()
    ids = state.get("thread_session_ids", [])
    if session_id not in ids:
        ids.append(session_id)
    state["thread_session_ids"] = ids[-20:]  # keep last 20
    _write_state(state)


def extract_ssh_target(command: str) -> str | None:
    """Parse 'ssh user@host' or 'ssh host' from a command string."""
    import shlex
    parts = shlex.split(command)
    if not parts or parts[0] not in ("ssh", "ssh.exe"):
        return None
    for p in parts[1:]:
        if not p.startswith("-") and "=" not in p:
            # could be user@host or just host
            host = p.split("@")[-1] if "@" in p else p
            # strip port if a:a appended (ssh -p case handled earlier)
            return host
    return None


def is_exit_command(command: str) -> bool:
    parts = command.strip().split()
    return bool(parts) and parts[0] in ("exit", "logout", "quit")
