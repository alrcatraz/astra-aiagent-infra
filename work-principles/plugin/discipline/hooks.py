"""work-principles plugin: lifecycle hooks.

pre_llm_call
  Injects phase-appropriate context into every LLM turn.

pre_tool_call
  Blocks out-of-phase tool use:
  - write_file / patch  → blocked unless phase=modifying/planning/closing
  - terminal(ssh/scp/…) → blocked unless phase=accessing_device/planning/modifying/closing

post_tool_call
  Auto-detects write_file/patch in EXECUTING → auto-transition to MODIFYING.

on_session_start
  Reset state to NO_TASK.
"""

from __future__ import annotations

import logging
import re

from .state import Phase, TRANSIENT_PHASES, get, set_phase, reset

logger = logging.getLogger("work-principles")

# ── Blocking rules ────────────────────────────────────────────────────
_MODIFYING_TOOLS = frozenset({"write_file", "patch"})
_SSH_RE = re.compile(r"(^|\s)(ssh|scp|rsync|sftp|telnet|mosh)(\s|$)")

# Phases where modifying tools are permitted
_MODIFY_ALLOWED = {Phase.MODIFYING, Phase.PLANNING, Phase.CLOSING}
# Phases where remote access is permitted — only when explicitly declared
_SSH_ALLOWED = {Phase.ACCESSING_DEVICE}

# ── Phase-to-message map ──────────────────────────────────────────────

def _message(phase: Phase, previous: str | None) -> str | None:
    text = _MESSAGE_TEMPLATES.get(phase)
    if text is None:
        return None
    if previous is not None and previous != Phase.NO_TASK.value:
        return text.format(previous=previous)
    return text


_MESSAGE_TEMPLATES: dict[Phase, str | None] = {
    Phase.NO_TASK: None,
    Phase.TASK_STARTED: (
        "⚙ Discipline: phase=task_started\n"
        "Research first. Check docs / tutorials, then propose a plan. "
        "Wait for approval before executing.\n"
        "→ skill_view('work-principles:pre-action-research')"
    ),
    Phase.PLANNING: (
        "⚙ Discipline: phase=planning\n"
        "Consult preferences and conventions. Show trade-offs. "
        "Get explicit approval before execution."
    ),
    Phase.ACCESSING_DEVICE: (
        "⚙ Discipline: phase=accessing_device  (prev: {previous})\n"
        "Check GPG credential store before asking the user. "
        "If new credentials obtained, save them.\n"
        "→ skill_view('work-principles:credential-store-management')"
    ),
    Phase.EXECUTING: None,
    Phase.MODIFYING: (
        "⚙ Discipline: phase=modifying  (prev: {previous})\n"
        "Back up first. Verify each step. Check for identical patterns.\n"
        "→ skill_view('work-principles:change-safeguard')"
    ),
    Phase.CLOSING: (
        "⚙ Discipline: phase=closing\n"
        "Credential leak scan. Skill update check. Decision record.\n"
        "→ skill_view('work-principles:work-closure-check')"
    ),
}


# ── Hook implementations ──────────────────────────────────────────────

def on_pre_tool_call(tool_name: str, args: dict | None = None, **kwargs):
    """Block tools that don't match the current phase."""
    state = get()
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current_phase = Phase(phase_name)
    except ValueError:
        return None

    # ── Block modifying tools in disallowed phases ──
    if tool_name in _MODIFYING_TOOLS and current_phase not in _MODIFY_ALLOWED:
        return {
            "action": "block",
            "message": (
                f"[work-principles] Blocked: {tool_name} requires phase=modifying "
                f"(current: {current_phase.value}). "
                f"Call discipline_set_phase('modifying', reason='...') first."
            ),
        }

    # ── Block remote access in disallowed phases ──
    if tool_name == "terminal":
        command = (args or {}).get("command", "")
        if current_phase not in _SSH_ALLOWED and _SSH_RE.search(command):
            cmd_preview = command[:80].replace("\n", "\\n")
            return {
                "action": "block",
                "message": (
                    f"[work-principles] Blocked: remote access requires "
                    f"phase=accessing_device (current: {current_phase.value}). "
                    f"Command: {cmd_preview}. "
                    f"Call discipline_set_phase('accessing_device', reason='...') first."
                ),
            }

    return None  # allow


def on_pre_llm_call(*args, **kwargs):
    """Inject phase-appropriate context into every LLM turn."""
    state = get()
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current_phase = Phase(phase_name)
    except ValueError:
        return None
    previous = state.get("previous_phase")

    msg = _message(current_phase, previous)
    if msg is None:
        return None

    reason = state.get("last_reason")
    if reason:
        msg += f"\n(reason: {reason})"

    return {"context": msg}


def on_post_tool_call(tool_name: str, args: dict | None = None, **kwargs):
    """Auto-detect phase transitions from tool usage."""
    if tool_name not in _MODIFYING_TOOLS:
        return

    state = get()
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current = Phase(phase_name)
    except ValueError:
        return

    if current in TRANSIENT_PHASES:
        return

    file_path = (args or {}).get("path", "?")
    set_phase(Phase.MODIFYING, f"auto: {tool_name}({file_path})")
    logger.info("auto-transition %s→modifying via %s(%s)", current.value, tool_name, file_path)


def on_session_start(session_id: str | None = None, **kwargs):
    """Reset state for a new session."""
    reset(session_id)
    logger.info("session start → no_task (session=%s)", session_id)
