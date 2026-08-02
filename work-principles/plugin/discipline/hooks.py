"""work-principles plugin: lifecycle hooks.

pre_llm_call
  Injects phase-appropriate context into every LLM turn.

pre_tool_call
  Blocks out-of-phase tool use:
  - research_detected → only research tools + read-only terminal
  - write_file / patch → blocked unless phase=modifying/planning/closing
  - terminal(ssh/scp/…) → blocked unless phase=accessing_device

post_tool_call
  - Auto-detects write/patch in EXECUTING → auto-transition to MODIFYING
  - Tool-Trigger auto-skill loading (browser→camofox, skill_manage→skill-creator, etc.)

post_llm_call
  - Detects [HARNESS:] markers in the assistant's final response and
    transitions phase.  This is the ONLY marker source.  Tool outputs are
    world content (file reads, search results) and are never scanned —
    otherwise reading the plugin's own source would trigger false
    transitions (e.g. the CLOSING template mentions the marker text).

on_session_start
  Reset state to NO_TASK.

Session isolation: every hook receives ``session_id=agent.session_id``
from Hermes.  We thread it explicitly through every state call — the
process-global ``HERMES_SESSION_ID`` env var is never used for isolation.
"""

from __future__ import annotations

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


def _session_from_kwargs(kwargs: dict) -> str | None:
    """Extract the per-session id Hermes injects into hook kwargs."""
    sid = kwargs.get("session_id") or kwargs.get("session") or ""
    return str(sid) or None


# ── Gate audit logging ──────────────────────────────────────────────────
import json as _json_audit
from datetime import datetime as _dt_audit

_GATE_AUDIT_LOG = Path.home() / ".hermes" / "persistent" / "gate-audit.log"


def _log_gate_block(gate: str, tool_name: str, phase: str,
                    command: str = "",
                    reason: str = "",
                    session_id: str | None = None) -> None:
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
            "session": (session_id or "")[:24],
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
    "psql": frozenset({  # Only SELECT/SHOW/EXPLAIN-style queries are read-only
        "-c", "--command",
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

    # Multi-word whitelist entries (e.g. "nmcli general", "python3 --version",
    # "git --version", "command -v") match as command prefixes.
    for entry in _READ_ONLY_COMMANDS:
        if " " in entry and (cmd == entry or cmd.startswith(entry + " ")):
            return True

    # Check always-read-only commands first (single-word entries)
    if base in _READ_ONLY_COMMANDS:
        return True

    # Check subcommand-based read-only patterns
    if base in _READ_ONLY_SUBCOMMANDS:
        allowed = _READ_ONLY_SUBCOMMANDS[base]
        if not allowed:
            # Empty set means the command itself is always read-only
            # (e.g. journalctl is always read-only)
            return True
        # Find the first non-option token (skips -C <path>, --no-pager, …)
        idx = 1
        while idx < len(tokens):
            tok = tokens[idx]
            if tok in ("-C", "-c") and idx + 1 < len(tokens) and base in ("git", "psql"):
                # git -C <dir> … / psql -c <query> … — skip flag + its argument
                sub = tokens[idx + 1].lower()
                if base == "psql":
                    # psql -c "<SQL>" — only SELECT/SHOW/EXPLAIN/DESCRIBE
                    stripped = sub.lstrip("() ")
                    if stripped.startswith(("select", "show", "explain",
                                            "describe", "\\d", "--")):
                        return True
                    return False
                idx += 2
                continue
            if tok.startswith("-"):
                # Flags that are themselves read-only markers (e.g. curl -I)
                if tok in allowed:
                    return True
                # Other flags: -p, --no-pager, --version, -h … are read-only
                # when they don't take a path argument we must skip.
                if tok in ("--no-pager", "--version", "--help", "-h", "-v",
                           "--short", "--stat", "--name-only", "--oneline",
                           "--format", "--pretty", "--date"):
                    idx += 1
                    continue
                if base == "git" and tok in ("-c", "--config") and idx + 1 < len(tokens):
                    idx += 2
                    continue
                if tok.startswith("--") and "=" in tok:
                    idx += 1
                    continue
                # Unknown flag — skip it (flags don't change read-only-ness
                # of the subcommand we're about to inspect)
                idx += 1
                continue
            break
        if idx >= len(tokens):
            return False
        sub = tokens[idx]
        if sub in allowed:
            return True
        # Check two-word pattern (e.g. "docker network ls")
        if idx + 1 < len(tokens):
            two_word = f"{tokens[idx]} {tokens[idx + 1]}"
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
        "If you need to modify files → call discipline_set_phase('modifying', ...)"
    ),
    Phase.MODIFYING: (
        "⚙ Discipline: phase=modifying  (prev: {previous})\n"
        "Back up first (change-safeguard). Verify each step. "
        "Check for identical patterns elsewhere.\n"
        "Complete modifications before leaving this phase."
    ),
    Phase.CLOSING: (
        "⚙ Discipline: phase=closing\n"
        "You MUST run the full closure checklist before finishing:\n"
        "  ⓪ System-config backup & credential leak scan\n"
        "  ① Skill update check\n"
        "  ② Decision record\n"
        "  ③ Service/device registration\n"
        "  ④ Information storage audit\n"
        "  ⑤ Environment baseline comparison\n"
        "  ⑥ Git commit housekeeping\n"
        "\n"
        "The CLOSING phase cannot be bypassed.  You must include\n"
        "[HARNESS: done] in your final response to exit this phase.\n"
        "Other [HARNESS:] markers (task_started/plan/casual) are\n"
        "rejected while in CLOSING."
    ),
}


# ── Hook implementations ──────────────────────────────────────────────

def on_pre_tool_call(tool_name: str, args: dict | None = None, **kwargs):
    """Block tools that don't match the current phase or research gate."""
    sid = _session_from_kwargs(kwargs)
    state = get(sid)
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
                            reason="non-readonly terminal during research",
                            session_id=sid)
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
                        reason="non-research tool during research",
                        session_id=sid)
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
                        reason=f"write tool in {current_phase.value}",
                        session_id=sid)
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
                            reason=f"remote access in {current_phase.value}",
                            session_id=sid)
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
                            reason="non-readonly terminal during closing",
                            session_id=sid)
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
                        reason=f"{tool_name} blocked during closing",
                        session_id=sid)
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
    sid = _session_from_kwargs(kwargs)
    state = get(sid)
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
        _write_state(state, sid)

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
        clear_closure_bypass(sid)

    return {"context": msg}


def _hook_arg(key: str, default: str = "", args=None, **kwargs) -> str:
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
    """Auto-detect phase transitions from tool usage.

    - write_file / patch → auto MODIFYING (when not already in transient)
    - Research tool use during research gate → track activity
    - Tool-trigger auto-skill loading

    NOTE: [HARNESS:] markers are NOT detected here — tool outputs are
    world content (file reads, search results) and scanning them caused
    false phase transitions.  Markers are detected exclusively in
    ``on_post_llm_call`` from the assistant's own response text.
    """
    sid = _session_from_kwargs(kwargs)
    state = get(sid)
    phase_name = state.get("phase", Phase.NO_TASK.value)
    try:
        current = Phase(phase_name)
    except ValueError:
        return

    if current in TRANSIENT_PHASES:
        return

    # ── Research gate: track research activity ──
    research_active = state.get("research_detected", False)
    if research_active and tool_name in _RESEARCH_TOOLS:
        set_research_activity(sid)

    # ── Auto-detect modifying from write_file/patch ──
    if tool_name in _MODIFYING_TOOLS and current != Phase.MODIFYING:
        file_path = _hook_arg("path", "?", args=args, **kwargs)
        set_phase(Phase.MODIFYING, f"auto: {tool_name}({file_path})", sid)
        logger.info("auto→modifying via %s(%s)", tool_name, file_path)
        return

    # ── Auto-load skill from tool triggers ──
    if tool_name in _TOOL_TRIGGER_SKILLS:
        skill = _TOOL_TRIGGER_SKILLS[tool_name]
        set_auto_loaded_skill(skill, sid)
        logger.info("auto-skill→%s via %s", skill, tool_name)

    # ── Auto-load skill from terminal command triggers ──
    if tool_name == "terminal":
        command = _hook_arg("command", "", args=args, **kwargs)
        if command:
            skill = _match_terminal_trigger(command)
            if skill:
                set_auto_loaded_skill(skill, sid)

    # ── Auto-load skill for skill_manage actions ──
    if tool_name == "skill_manage":
        action = _hook_arg("action", "", args=args, **kwargs)
        if action in _TOOL_ACTION_SKILLS.get("skill_manage", frozenset()):
            # Will be picked up by pre_llm_call reminder
            state["skill_manage_pending"] = action
            from .state import _write as _write_state
            _write_state(state, sid)
            # Also auto-load skill-creator
            set_auto_loaded_skill("skill-creator", sid)
            logger.info("auto-skill→skill-creator via skill_manage(%s)", action)

    # ── Research/exploration tools → auto TASK_STARTED (from NO_TASK) ──
    if current == Phase.NO_TASK and tool_name in (
        "web_search", "session_search", "skill_view",
    ):
        set_phase(Phase.TASK_STARTED, f"auto: {tool_name}", sid)
        set_research_detected(sid)
        logger.info("auto→task_started via %s", tool_name)


def on_post_llm_call(*args, assistant_response: str | None = None, **kwargs):
    """Detect [HARNESS:] markers in the assistant's final response.

    This is the ONLY source of [HARNESS:] marker detection.  Tool outputs
    are never scanned (see module docstring).
    """
    sid = _session_from_kwargs(kwargs)
    if not assistant_response:
        return None
    marker = _detect_harness_markers(assistant_response)
    if not marker:
        return None
    state = get(sid)
    try:
        current = Phase(state.get("phase", Phase.NO_TASK.value))
    except ValueError:
        return None
    _handle_harness_marker(marker, current, sid)
    return None


def _handle_harness_marker(marker: str,
                            current: Phase,
                            session_id: str | None = None) -> None:
    """Process a [HARNESS:] marker and transition phase accordingly.

    If currently in CLOSING phase and the marker is not 'done', this
    is treated as an attempt to bypass closure — the warning flag is
    set so pre_llm_call can inject a reminder on the next turn.
    """
    # Detect closure bypass: in CLOSING, only [HARNESS: done] is valid
    if current == Phase.CLOSING and marker != "done":
        set_closure_bypass(session_id)
        logger.info("closure bypass attempty → marker=%s (still in %s)",
                     marker, current.value)
        return

    if marker == "task_started":
        set_phase(Phase.TASK_STARTED, "harness: task_started marker", session_id)
        set_research_detected(session_id)
    elif marker == "plan":
        set_phase(Phase.PLANNING, "harness: plan marker", session_id)
        clear_research_detected(session_id)
    elif marker == "casual":
        reset(session_id)
    elif marker == "done":
        set_phase(Phase.CLOSING, "harness: done marker", session_id)
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
