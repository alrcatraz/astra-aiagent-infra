"""work-principles plugin: state machine — phase definitions and persistence.

Each Hermes session uses its own state file (state_{session_id}.json) to
prevent cross-session interference.  Sessions without HERMES_SESSION_ID
fall back to the shared state.json.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path

PERSISTENT_DIR = Path.home() / ".hermes" / "persistent"
STATE_FILE = PERSISTENT_DIR / "state.json"
_lock = threading.Lock()


class Phase(str, Enum):
    """Work phases for the discipline state machine.

    Steady states (no context injection by default):
        NO_TASK    — idle / casual conversation
        EXECUTING  — running the approved plan

    Transient states (save previous_phase to return to):
        ACCESSING_DEVICE — need device/credential access
        MODIFYING        — about to modify system config or files

    Transition states (context injected):
        TASK_STARTED — new task; research gate active
        PLANNING    — research done; propose, wait for approval
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


def _current_session_id() -> str | None:
    return os.environ.get("HERMES_SESSION_ID") or None


def _state_path() -> Path:
    sid = _current_session_id()
    if sid:
        return PERSISTENT_DIR / f"state_{sid}.json"
    return STATE_FILE


def _ensure_dir() -> None:
    PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)


def _write(state: dict) -> None:
    now = datetime.now().isoformat()
    state["updated_at"] = now
    path = _state_path()
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def default_state() -> dict:
    return {
        "phase": Phase.NO_TASK.value,
        "previous_phase": None,
        "phase_changed_at": None,
        "last_reason": None,
        "updated_at": None,
        "session_id": None,
        # Research gate: when True, only research tools + read-only terminal
        # are permitted.  Cleared by [HARNESS: plan] or after research done.
        "research_detected": False,
        # Track whether at least one research tool has been used this turn
        "research_activity_this_turn": False,
        # Tool-triggered auto-loaded skill — injected next pre_llm_call
        "auto_loaded_skill": None,
    }


def get() -> dict:
    """Read current state (thread-safe) from the per-session file."""
    _ensure_dir()
    path = _state_path()
    try:
        state = json.load(open(path))
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        state = default_state()
        _write(state)
        return state


def set_phase(phase: Phase, reason: str | None = None,
              session_id: str | None = None) -> dict:
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

        if session_id:
            state["session_id"] = session_id
        else:
            current_sid = _current_session_id()
            if current_sid:
                state["session_id"] = current_sid

        _write(state)

    return state


def reset(session_id: str | None = None) -> dict:
    """Reset to NO_TASK for a new session."""
    state = default_state()
    state["session_id"] = session_id
    _write(state)
    return state


# ── Research gate helpers ──────────────────────────────────────────────

def set_research_detected() -> None:
    """Activate the research gate for the current session."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["research_detected"] = True
        state["research_activity_this_turn"] = False
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def clear_research_detected() -> None:
    """Deactivate the research gate — agent may now execute."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["research_detected"] = False
        state["research_activity_this_turn"] = False
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def set_research_activity() -> None:
    """Mark that at least one research tool was used this turn."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["research_activity_this_turn"] = True
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def set_auto_loaded_skill(skill_name: str) -> None:
    """Record a tool-triggered auto-loaded skill for injection next turn."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["auto_loaded_skill"] = skill_name
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def set_closure_bypass() -> None:
    """Mark that the agent tried to skip the closing checklist."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["closure_bypass_warning"] = True
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def clear_closure_bypass() -> None:
    """Clear the closure bypass warning."""
    with _lock:
        state = default_state()
        path = _state_path()
        try:
            existing = json.load(open(path))
            state.update(existing)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        state["closure_bypass_warning"] = False
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
