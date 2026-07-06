"""work-principles plugin: state machine — phase definitions and persistence."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path

PERSISTENT_DIR = Path.home() / ".hermes" / "persistent"
STATE_FILE = PERSISTENT_DIR / "state.json"
_lock = threading.Lock()


class Phase(str, Enum):
    """Work phases for the discipline state machine.

    Steady states (silent — no context injection):
        NO_TASK    — idle / casual conversation
        EXECUTING  — running the approved plan, no modifications

    Transient states (context injected; save previous_phase to return to):
        ACCESSING_DEVICE — need device/credential access
        MODIFYING        — about to modify system config or files

    Transition states (context injected):
        TASK_STARTED — new task discovered; research first
        PLANNING    — research done; consult preferences, propose, wait for approval
        CLOSING     — task complete; run closure checks
    """
    NO_TASK = "no_task"
    TASK_STARTED = "task_started"
    PLANNING = "planning"
    ACCESSING_DEVICE = "accessing_device"
    EXECUTING = "executing"
    MODIFYING = "modifying"
    CLOSING = "closing"


# Phases that capture and restore a previous_phase
TRANSIENT_PHASES: set[Phase] = {Phase.ACCESSING_DEVICE, Phase.MODIFYING}


def _ensure_dir() -> None:
    PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)


def _write(state: dict) -> None:
    now = datetime.now().isoformat()
    state["updated_at"] = now
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def default_state() -> dict:
    return {
        "phase": Phase.NO_TASK.value,
        "previous_phase": None,
        "phase_changed_at": None,
        "last_reason": None,
        "updated_at": None,
        "session_id": None,
    }


def get() -> dict:
    """Read current state (thread-safe)."""
    _ensure_dir()
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = default_state()
        _write(state)
        return state


def set_phase(phase: Phase, reason: str | None = None) -> dict:
    """Transition to a new phase.

    - Entering a TRANSIENT phase saves ``previous_phase`` (unless already
      inside a transient — no double-wrapping).
    - Leaving a TRANSIENT phase clears ``previous_phase``.
    """
    with _lock:
        state = get()
        current = Phase(state.get("phase", Phase.NO_TASK.value))

        if phase in TRANSIENT_PHASES:
            if current not in TRANSIENT_PHASES:
                state["previous_phase"] = current.value
        else:
            if current in TRANSIENT_PHASES:
                state["previous_phase"] = None

        now = datetime.now().isoformat()
        state["phase"] = phase.value
        state["phase_changed_at"] = now
        state["last_reason"] = reason
        _write(state)

    return state


def reset(session_id: str | None = None) -> dict:
    """Reset to NO_TASK for a new session."""
    state = default_state()
    state["session_id"] = session_id
    _write(state)
    return state
