"""work-principles plugin: lifecycle hooks.

pre_llm_call
  Injects phase-appropriate context into every LLM turn.

pre_tool_call
  Blocks out-of-phase tool use:
  - research_detected → only research tools + read-only terminal
  - write_file / patch → blocked unless phase=modifying/planning/closing
  - terminal(ssh/scp/…) → blocked unless phase=accessing_device

post_tool_call
  - Detects [HARNESS:] markers in output → transitions phase
  - Auto-detects write/patch in EXECUTING → auto-transition to MODIFYING
  - Tool-Trigger auto-skill loading (browser→camofox, skill_manage→skill-creator, etc.)

on_session_start
  Reset state to NO_TASK.
"""

from __future__ import annotations

import json as _json
import logging
import re
from pathlib import Path

from .state import (
    Phase,
    TRANSIENT_PHASES,
    get,
    set_phase,
    reset,
    set_research_detected,
    clear_research_detected,
    set_research_activity,
    set_auto_loaded_skill,
    set_closure_bypass,
    clear_closure_bypass,
)

logger = logging.getLogger("work-principles")

# ── Gate audit logging ──────────────────────────────────────────────────
import json as _json_audit
from datetime import datetime as _dt_audit

_GATE_AUDIT_LOG = Path.home() / ".hermes" / "persistent" / "gate-audit.log"


def _log_gate_block(gate: str, tool_name: str, phase: str,
                    command: str = "",
                    reason: str = "") -> None:
    """Append a structured JSON line to the gate audit log."""
    try:
        _GATE_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "t": _dt_audit.now().isoformat(),
            "gate": gate,
            "tool": tool_name,
            "phase": phase,
            "cmd": command[:120],
            "reason": reason[:200],
        }
        with open(_GATE_AUDIT_LOG, "a") as f:
            f.write(_json_audit.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # audit logging is best-effort


# ── Read-only command whitelist ─────────────────────────────────────────
# Commands that are ALWAYS safe to run during research phase, regardless of
# arguments.  Each entry is checked as a prefix (command starts with it).

_READ_ONLY_COMMANDS = frozenset({
    # System inspection
    "cat", "head", "tail", "less", "more",
    "which", "type", "whereis", "command -v",
    "file", "stat", "wc", "sort", "uniq", "cut", "tr",
    "readlink", "realpath", "od", "xxd", "strings",
    # Process inspection
    "ps", "pgrep", "pidof", "lsof", "fuser",
    "top", "htop", "uptime",
    # Resource inspection
    "df", "du", "free",
    "uname", "hostname", "whoami", "id",
    "getconf", "nproc", "lscpu", "lsblk", "lspci", "lsusb", "lsmod",
    "sysctl", "dmesg",
    # Network inspection (read-only variants)
    "ss", "dig", "nslookup", "host",
    "nmcli general", "nmcli device status",
    "fc-list", "fc-match", "pkg-config",
    "locale", "timedatectl", "resolvectl status",
    "nvidia-smi", "vulkaninfo", "glxinfo",
    # Version checks
    "python3 --version", "python --version",
    "node --version", "uv --version",
    "git --version", "docker --version", "podman --version",
    "date", "env", "echo", "printf",
    "pwd", "ls",
    # Search / find (read-only)
    "grep", "find", "locate",
})

# Commands whose FIRST subcommand determines read/write nature
_READ_ONLY_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "git": frozenset({
        "status", "log", "diff", "branch", "remote",
        "show", "stash", "tag", "ls-remote", "ls-files",
        "shortlog", "describe", "name-rev",
        "config --list", "config --get",
    }),
    "docker": frozenset({
        "ps", "images", "inspect", "logs", "info",
        "network ls", "volume ls", "version",
        "stats", "events", "port", "top",
    }),
    "podman": frozenset({
        "ps", "images", "inspect", "logs", "info",
        "network ls", "volume ls", "version",
        "stats", "events", "port", "top",
    }),
    "systemctl": frozenset({
        "status", "is-active", "is-enabled",
        "list-units", "list-dependencies", "list-sockets",
        "show", "cat",
    }),
    "journalctl": frozenset(),  # always read-only
    "ip": frozenset({
        "addr", "link", "route", "neigh", "maddr",
    }),
    "curl": frozenset({  # Only truly read-only curl invocations
        "-I", "--head", "--help",
    }),
    "wget": frozenset({
        "--spider",
    }),
}

# Tools that are always allowed during research (research tools)
_RESEARCH_TOOLS = frozenset({
    "skill_view", "skills_list",
    "web_search", "web_extract",
    "session_search",
    "fact_store", "fact_feedback",
    "memory",
    "read_file", "search_files",
    "vision_analyze",
    "browser_navigate", "browser_snapshot",
    "browser_click", "browser_type",
    "browser_scroll", "browser_back",
    "browser_console", "browser_vision", "browser_get_images",
    "mcp_kb_search",
    "todo",
    "discipline_set_phase",
    "clarify",
    "text_to_speech",
})

# Tools that modify files — blocked unless in an allowed phase
_MODIFYING_TOOLS = frozenset({"write_file", "patch"})

# Phases where modifying tools are permitted
_MODIFY_ALLOWED = {Phase.MODIFYING, Phase.PLANNING, Phase.CLOSING}

# Phases where remote access is permitted
_SSH_ALLOWED = {Phase.ACCESSING_DEVICE}

_SSH_RE = re.compile(r"(^|\s)(ssh|scp|rsync|sftp|telnet|mosh)(\s|$)")


# ── Read-only terminal detection ───────────────────────────────────────

def _is_read_only_command(command: str) -> bool:
    """Check if a terminal command is safe to run during research phase."""
    cmd = command.strip()
    # Strip leading sudo/time/nohup
    for prefix in ("sudo ", "time ", "nohup "):
        if cmd.startswith(prefix):
            cmd = cmd[len(prefix):]
            break

    # Tokenise
    try:
        import shlex
        tokens = shlex.split(cmd)
    except (ValueError, ImportError):
        tokens = cmd.split()
    if not tokens:
        return False

    base = tokens[0]

    # Check always-read-only commands first
    if base in _READ_ONLY_COMMANDS:
        return True

    # Check subcommand-based read-only patterns
    if base in _READ_ONLY_SUBCOMMANDS:
        allowed = _READ_ONLY_SUBCOMMANDS[base]
        if not allowed:
            # Empty set means the command itself is always read-only
            # (e.g. journalctl is always read-only)
            return True
        if len(tokens) >= 2:
            # Check first subcommand
            sub = tokens[1]
            if sub in allowed:
                return True
            # Check two-word pattern (e.g. "docker network ls")
            if len(tokens) >= 3:
                two_word = f"{tokens[1]} {tokens[2]}"
                if two_word in allowed:
                    return True

    return False


# ── [HARNESS:] marker detection ────────────────────────────────────────

_HARNESS_MARKER_RE = re.compile(
    r'\[HARNESS:\s*(task_started|plan|casual|done)\]'
)


def _detect_harness_markers(text: str) -> str | None:
    """Extract [HARNESS:] marker from text, if any."""
    m = _HARNESS_MARKER_RE.search(text)
    if m:
        return m.group(1)
    return None


# ── Tool-trigger auto-skill patterns ────────────────────────────────────

# When these tools are called, auto-load the corresponding skill
_TOOL_TRIGGER_SKILLS: dict[str, str] = {
    "browser_navigate": "camofox-browser",
    "browser_click": "camofox-browser",
    "browser_type": "camofox-browser",
    "browser_vision": "camofox-browser",
    "browser_snapshot": "camofox-browser",
}

# Regex patterns for terminal commands → auto-load skill
_TERMINAL_TRIGGER_SKILLS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(keepass|keepassxc|gpg\s*--decrypt|password-store)'), "credential-store-management"),
]

# Tool name + action → auto-load skill
_TOOL_ACTION_SKILLS: dict[str, frozenset[str]] = {
    "skill_manage": frozenset({"create", "edit", "patch"}),
}

# Tools allowed during CLOSING phase (beyond research tools + read-only terminal)
_CLOSING_TOOLS = frozenset({
    "skill_manage",
    "todo",
    "memory",
    "fact_store",
    "fact_feedback",
    "clarify",
    "text_to_speech",
})


# ── Phase-to-message map ──────────────────────────────────────────────

def _message(phase: Phase, previous: str | None,
             research_active: bool = False,
             auto_skill: str | None = None) -> str | None:
    text = _MESSAGE_TEMPLATES.get(phase)
    if text is None:
        return None

    parts = []

    if phase == Phase.TASK_STARTED:
        parts.append(text)
        if research_active:
            parts.append(
                "🔒 Research gate active — only research tools and read-only "
                "terminal commands are permitted until [HARNESS: plan]."
            )
    elif previous is not None and previous != Phase.NO_TASK.value:
        parts.append(text.format(previous=previous))
    else:
        parts.append(text)

    if auto_skill:
        parts.append(
            f"📖 Auto-loaded: skill_view('{auto_skill}') — loaded because "
            "a related tool was used."
        )

    return "\n".join(parts)


_MESSAGE_TEMPLATES: dict[Phase, str | None] = {
    Phase.NO_TASK: None,
    Phase.TASK_STARTED: (
        "⚙ Discipline: phase=task_started\n"
        "Research first. Check docs / tutorials, then propose a plan. "
        "Wait for approval before executing."
    ),
    Phase.PLANNING: (
        "⚙ Discipline: phase=planning\n"
        "Consult preferences and conventions. Show trade-offs. "
        "Get explicit approval before execution.\n"
        "Write your plan into the todo list: "
        "todo(todos=[{id:'step-1', content:'...', status:'pending'}, ...], merge=true).\n"
        "Use ↳ prefix + step-N.M IDs for sub-tasks."
    ),
    Phase.ACCESSING_DEVICE: (
        "⚙ Discipline: phase=accessing_device  (prev: {previous})\n"
        "Check GPG credential store before asking the user. "
        "If new credentials obtained, save them."
    ),
    Phase.EXECUTING: (
        "⚙ Discipline: phase=executing\n"
        "Reminders — execute step by step:\n"
        "  ✅ Step transparency: explain before acting\n"
        "  ✅ Progressive verification: verify after each step\n"
        "  ✅ Dependency-first: bottom-up when troubleshooting\n"
        "  ✅ Skill-first: load a skill if one exists for the operation\n"
        "If you need to modify files → call discipline_set_phase('modifying', ...)"
    ),
    Phase.MODIFYING: (
        "⚙ Discipline: phase=modifying  (prev: {previous})\n"
        "Back up first (change-safeguard). Verify each step. "
        "Check for identical patterns elsewhere.\n"
        "Complete modifications before leaving this phase."
    ),
    Phase.CLOSING: (
        "⚙ Discipline: phase=closing\\n"
        "You MUST run the full closure checklist before finishing:\\n"
        "  ⓪ System-config backup & credential leak scan\\n"
        "  ① Skill update check\\n"
        "  ② Decision record\\n"
        "  ③ Service/device registration\\n"
        "  ④ Information storage audit\\n"
        "  ⑤ Environment baseline comparison\\n"
        "  ⑥ Git commit housekeeping\\n"
        "\\n"
        "The CLOSING phase cannot be bypassed.  You must include\\n"
        "[HARNESS: done] in your final response to exit this phase.\\n"
        "Other [HARNESS:] markers (task_started/plan/casual) are\\n"
        "rejected while in CLOSING."
    ),
}


# ── Hook implementations ──────────────────────────────────────────────

def on_pre_tool_call(tool_name: str, args: dict | None = None, **kwargs):
    """Block tools that don't match the current phase or research gate."""
    state = get()
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current_phase = Phase(phase_name)
    except ValueError:
        return None

    # ── Research gate enforcement ──
    research_active = state.get("research_detected", False)
    if research_active:
        # Research tools always allowed
        if tool_name in _RESEARCH_TOOLS:
            return None

        # Terminal: allow only read-only commands
        if tool_name == "terminal":
            command = (args or {}).get("command", "")
            if _is_read_only_command(command):
                return None
            _log_gate_block("research", tool_name,
                            current_phase.value,
                            command=command,
                            reason="non-readonly terminal during research")
            return {
                "action": "block",
                "message": (
                    "[work-principles] Research gate: only read-only terminal "
                    "commands are permitted during research. "
                    f"Command blocked: {command[:80]}"
                ),
            }

        # All other tools blocked during research unless in whitelist
        _log_gate_block("research", tool_name,
                        current_phase.value,
                        reason="non-research tool during research")
        return {
            "action": "block",
            "message": (
                f"[work-principles] Research gate: {tool_name} requires "
                "research to be completed first. "
                "Use research tools (skill_view, web_search, read-only "
                "terminal, etc.) and then include [HARNESS: plan] to proceed."
            ),
        }

    # ── Block modifying tools in disallowed phases ──
    if tool_name in _MODIFYING_TOOLS and current_phase not in _MODIFY_ALLOWED:
        _log_gate_block("modify", tool_name,
                        current_phase.value,
                        reason=f"write tool in {current_phase.value}")
        return {
            "action": "block",
            "message": (
                f"[work-principles] Blocked: {tool_name} requires "
                f"phase=modifying (current: {current_phase.value}). "
                "Call discipline_set_phase('modifying', reason='...') first."
            ),
        }

    # ── Block remote access in disallowed phases ──
    if tool_name == "terminal":
        command = (args or {}).get("command", "")
        if current_phase not in _SSH_ALLOWED and _SSH_RE.search(command):
            cmd_preview = command[:80].replace("\n", "\\n")
            _log_gate_block("ssh", tool_name, current_phase.value,
                            command=command,
                            reason=f"remote access in {current_phase.value}")
            return {
                "action": "block",
                "message": (
                    f"[work-principles] Blocked: remote access requires "
                    f"phase=accessing_device (current: {current_phase.value}). "
                    f"Command: {cmd_preview}. "
                    "Call discipline_set_phase('accessing_device', reason='...') first."
                ),
            }

    # ── Closure gate: in CLOSING phase, restrict to research/safe tools ──
    if current_phase == Phase.CLOSING:
        # Research tools always allowed
        if tool_name in _RESEARCH_TOOLS:
            return None
        # Terminal: allow only read-only
        if tool_name == "terminal":
            command = (args or {}).get("command", "")
            if _is_read_only_command(command):
                return None
            _log_gate_block("closure", tool_name, current_phase.value,
                            command=command,
                            reason="non-readonly terminal during closing")
            return {
                "action": "block",
                "message": (
                    "[work-principles] Closure gate: only read-only terminal "
                    "commands are permitted during closing. "
                    f"Blocked: {command[:80]}"
                ),
            }
        # Explicitly allowed closure tools
        if tool_name in _CLOSING_TOOLS:
            return None
        # Everything else blocked
        _log_gate_block("closure", tool_name, current_phase.value,
                        reason=f"{tool_name} blocked during closing")
        return {
            "action": "block",
            "message": (
                f"[work-principles] Closure gate: {tool_name} is not permitted "
                "during the closing phase. Complete the closure checklist and "
                "include [HARNESS: done] in your response to finish."
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
    research_active = state.get("research_detected", False)
    auto_skill = state.get("auto_loaded_skill")

    msg = _message(current_phase, previous,
                   research_active=research_active,
                   auto_skill=auto_skill)

    # Clear the auto-loaded skill after injection (one-shot)
    if auto_skill:
        state["auto_loaded_skill"] = None
        from .state import _write as _write_state
        _write_state(state)

    if msg is None:
        return None

    reason = state.get("last_reason")
    if reason:
        msg += f"\n(reason: {reason})"

    # ── skill_manage follow-up reminder ──
    _sm_pending = state.get("skill_manage_pending")
    if _sm_pending:
        msg += (
            "\n\n🛠 Skill management reminder: you just used "
            f"skill_manage(action='{_sm_pending}').\n"
            "Load the 'skill-creator' skill (skill_view('skill-creator')) to "
            "ensure frontmatter is complete."
        )
        state["skill_manage_pending"] = None

    # ── Closure bypass warning ──
    if state.get("closure_bypass_warning"):
        msg += (
            "\n\n⚠️  Closure bypass detected: you attempted to finish without "
            "completing the closure checklist.\n"
            "The CLOSING phase will not advance until you include "
            "[HARNESS: done] in your response."
        )
        clear_closure_bypass()

    return {"context": msg}


def _hook_arg(key: str, default: str = "", args=None) -> str:
    """Safely extract a key from the args dict.

    Hermes post_tool_call may pass the result string as the second
    positional argument instead of the actual args dict.  Guard against
    that so the hook doesn't crash on every tool call.
    """
    candidates = []
    if isinstance(args, dict):
        candidates.append(args)
    for v in kwargs.values():
        if isinstance(v, dict):
            candidates.append(v)
    for d in candidates:
        val = d.get(key)
        if val is not None:
            return str(val)
    return default


def on_post_tool_call(tool_name: str, args: dict | None = None,
                      result=None, **kwargs):
    """Auto-detect phase transitions from tool usage and [HARNESS:] markers.

    - [HARNESS: task_started] → TASK_STARTED + activate research gate
    - [HARNESS: plan] → PLANNING + clear research gate
    - [HARNESS: casual] → NO_TASK (reset)
    - [HARNESS: done] → CLOSING
    - write_file / patch → auto MODIFYING (when not already in transient)
    - Research tool use during research gate → track activity
    - Tool-trigger auto-skill loading
    """
    state = get()
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current = Phase(phase_name)
    except ValueError:
        return

    if current in TRANSIENT_PHASES:
        return

    # ── [HARNESS:] marker detection from terminal output ──
    if tool_name == "terminal":
        output = (result or {}).get("output", "") if isinstance(result, dict) else ""
        marker = _detect_harness_markers(output)
        if marker:
            _handle_harness_marker(marker, current)
            return

    # ── [HARNESS:] marker detection from any response ──
    # Check both result and kwargs for the marker
    if isinstance(result, dict):
        text = result.get("output", "") or result.get("content", "")
    else:
        text = str(result or "")
    marker = _detect_harness_markers(text)
    if marker:
        _handle_harness_marker(marker, current)
        return

    # ── Research gate: track research activity ──
    research_active = state.get("research_detected", False)
    if research_active and tool_name in _RESEARCH_TOOLS:
        set_research_activity()

    # ── Auto-detect modifying from write_file/patch ──
    if tool_name in _MODIFYING_TOOLS and current != Phase.MODIFYING:
        file_path = _hook_arg("path", "?", args=args, **kwargs)
        set_phase(Phase.MODIFYING, f"auto: {tool_name}({file_path})")
        logger.info("auto→modifying via %s(%s)", tool_name, file_path)
        return

    # ── Auto-load skill from tool triggers ──
    if tool_name in _TOOL_TRIGGER_SKILLS:
        skill = _TOOL_TRIGGER_SKILLS[tool_name]
        set_auto_loaded_skill(skill)
        logger.info("auto-skill→%s via %s", skill, tool_name)

    # ── Auto-load skill from terminal command triggers ──
    if tool_name == "terminal":
        command = _hook_arg("command", "", args=args, **kwargs)
        if command:
            skill = _match_terminal_trigger(command)
            if skill:
                set_auto_loaded_skill(skill)

    # ── Auto-load skill for skill_manage actions ──
    if tool_name == "skill_manage":
        action = _hook_arg("action", "", args=args, **kwargs)
        if action in _TOOL_ACTION_SKILLS.get("skill_manage", frozenset()):
            # Will be picked up by pre_llm_call reminder
            state["skill_manage_pending"] = action
            from .state import _write as _write_state
            _write_state(state)
            # Also auto-load skill-creator
            set_auto_loaded_skill("skill-creator")
            logger.info("auto-skill→skill-creator via skill_manage(%s)", action)

    # ── Research/exploration tools → auto TASK_STARTED (from NO_TASK) ──
    if current == Phase.NO_TASK and tool_name in (
        "web_search", "session_search", "skill_view",
    ):
        set_phase(Phase.TASK_STARTED, f"auto: {tool_name}")
        set_research_detected()
        logger.info("auto→task_started via %s", tool_name)


def _handle_harness_marker(marker: str,
                            current: Phase) -> None:
    """Process a [HARNESS:] marker and transition phase accordingly.

    If currently in CLOSING phase and the marker is not 'done', this
    is treated as an attempt to bypass closure — the warning flag is
    set so pre_llm_call can inject a reminder on the next turn.
    """
    # Detect closure bypass: in CLOSING, only [HARNESS: done] is valid
    if current == Phase.CLOSING and marker != "done":
        set_closure_bypass()
        logger.info("closure bypass attempty → marker=%s (still in %s)",
                     marker, current.value)
        return

    if marker == "task_started":
        set_phase(Phase.TASK_STARTED, "harness: task_started marker")
        set_research_detected()
    elif marker == "plan":
        set_phase(Phase.PLANNING, "harness: plan marker")
        clear_research_detected()
    elif marker == "casual":
        reset()
    elif marker == "done":
        set_phase(Phase.CLOSING, "harness: done marker")
    logger.info("harness marker→%s (phase=%s)", marker, current.value)


def _match_terminal_trigger(command: str) -> str | None:
    """Check terminal command against trigger patterns for auto-skill load."""
    for pattern, skill in _TERMINAL_TRIGGER_SKILLS:
        if pattern.search(command):
            return skill
    return None


def on_session_start(session_id: str | None = None, **kwargs):
    """Reset state for a new session."""
    reset(session_id)
    logger.info("session start → no_task (session=%s)", session_id)
