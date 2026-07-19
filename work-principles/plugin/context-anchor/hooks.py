"""Context-anchor hooks for Hermes plugin system.

on_pre_llm_call:   Injects a [CONTEXT ANCHOR] block into the system prompt
                   with per-session mission, host, task, key facts, and last tool.

on_post_tool_call: Tracks ALL tools, detects SSH enter/exit, infers task from
                   terminal commands, and parses #anchor: annotations.

v2.1.0 — Fully per-session via database backend. No cross-session contamination.
"""

from .state import (
    get_state, set_host, record_session, set_task, set_mission, set_last_tool,
    add_fact, remove_fact, clear_facts, teardown,
    extract_ssh_target, is_exit_command, parse_anchor_annotations,
)
import subprocess
from datetime import datetime, timezone

LOG_PREFIX = "[context-anchor]"

_TOOL_PREFIXES = frozenset({"sudo", "time", "nohup", "setsid", "env", "noglob", "doas"})
_SSH_LIKE = frozenset({"ssh", "sshpass", "scp", "rsync", "sftp"})


# ── Helpers ─────────────────────────────────────────────────────────


def _infer_task(command: str) -> str:
    """Extract 'verb:subject' from any terminal command."""
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return "noop"
    while tokens and tokens[0] in _TOOL_PREFIXES:
        tokens.pop(0)
    if not tokens:
        return "noop"
    verb = tokens[0]
    if verb in _SSH_LIKE:
        for t in tokens[1:]:
            if not t.startswith("-") and "=" not in t:
                target = t.split("@")[-1].split(":")[0]
                return f"ssh:{target}"
        return "ssh"
    pipe_at = None
    for i, t in enumerate(tokens):
        if t == "|":
            pipe_at = i
            break
    search_until = pipe_at if pipe_at is not None else len(tokens)
    for t in tokens[1:search_until]:
        if t.startswith("-"):
            continue
        if t in {">", ">>", "<", "2>", "&>", "|", ";", "&&", "||"}:
            continue
        subj = _shorten(t)
        return f"{verb}:{subj}"
    return verb


def _shorten(s: str) -> str:
    if s.startswith(("http://", "https://")):
        after = s.split("//", 1)[-1] if "//" in s else s
        return after.split("/")[0].split(":")[0]
    if "/" in s:
        base = s.rstrip("/").split("/")[-1]
        return base[:32] + "..." if len(base) > 35 else base
    if " " in s and not s.startswith(("'", '"')):
        return s.split()[0]
    return s[:32] + "..." if len(s) > 35 else s


def _debounce_task_update(state: dict, new_task: str) -> bool:
    """Return True if current_task should be updated (5-min debounce)."""
    cur = state.get("current_task", "")
    if cur == new_task:
        return False
    if cur in ("awaiting-user-input", "testing", ""):
        return True
    updated_at = state.get("updated_at", "")
    if updated_at:
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - updated).total_seconds()
            if elapsed < 300:
                return False
        except (ValueError, TypeError):
            pass
    return True


def _build_anchor_block(state: dict) -> str:
    """Build a structured [CONTEXT ANCHOR] block from per-session state."""
    host = state.get("current_host", "unknown")
    local = state.get("local_host", "")
    task = state.get("current_task", "awaiting-user-input")
    mission = state.get("current_mission", "")
    last_tool = state.get("last_tool", "")
    facts = state.get("key_facts", {})

    if local and host and host != local:
        host_line = f"Host:      {local} → ssh:{host}"
    else:
        host_line = f"Host:      {host}"

    mission_line = f"Mission:   {mission}" if mission else "Mission:   (not set — use #anchor:mission <text>)"
    task_line = f"Current:   {task}"
    tool_line = f"Last tool: {last_tool}" if last_tool else ""

    lines = ["[CONTEXT ANCHOR]"]
    lines.append(f"  {mission_line}")
    lines.append(f"  {task_line}")
    lines.append(f"  {host_line}")
    if tool_line:
        lines.append(f"  {tool_line}")
    if facts:
        lines.append("  Key Facts:")
        for k in sorted(facts.keys()):
            lines.append(f"    • {k}: {facts[k]}")
    lines.append("[/CONTEXT ANCHOR]")
    return "\n".join(lines)


# ── Tool call summariser ───────────────────────────────────────────


def _summarise_tool_args(tool_name: str, args: dict | None) -> str:
    if not args:
        return ""
    if tool_name == "terminal":
        cmd = args.get("command", "")
        return cmd[:47] + "..." if len(cmd) > 50 else cmd
    if tool_name in ("read_file", "write_file"):
        return args.get("path", "")
    if tool_name == "web_search":
        return f'"{args.get("query", "")[:40]}"'
    if tool_name == "web_extract":
        urls = args.get("urls", [])
        return urls[0][:50] if urls else ""
    if tool_name == "session_search":
        q = args.get("query", "")
        return f'"{q[:40]}"' if q else "browse"
    if tool_name in ("skill_view", "skill_manage"):
        return args.get("name", "")
    if tool_name == "vision_analyze":
        return args.get("image_url", "")[:40]
    return ""


# ── Hooks ──────────────────────────────────────────────────────────


def on_pre_llm_call(*args, **kwargs) -> str:
    """Inject [CONTEXT ANCHOR] block before each LLM call.

    Attempts to read session_id from kwargs. Falls back to empty
    template if unavailable (safe — no crash, just no saved context).
    """
    session_id = kwargs.get("session_id") or kwargs.get("session", "")
    state = get_state(session_id) if session_id else get_state(None)
    block = _build_anchor_block(state)
    header = f"\n\n{block}\n"
    if args:
        return args[0] + header
    return (kwargs.get("system_prompt", "") or "") + header


def on_post_tool_call(tool_name: str, args: dict | None = None, result: str = None, **kwargs):
    """Track tools, detect SSH/exit, parse annotations.

    All state operations are scoped to session_id from kwargs.
    """
    session_id = kwargs.get("session_id") or kwargs.get("session", "")
    if not session_id:
        return  # can't persist without a session id

    _a = args if isinstance(args, dict) else {}
    command = _a.get("command", "") or (result or "")

    # Ensure session row exists
    state = get_state(session_id)
    record_session(session_id, local_hostname=state.get("local_host", ""))

    # ── Parse #anchor: annotations ────────────────────────────
    if tool_name == "terminal" and command:
        annotations = parse_anchor_annotations(command)
        for action, ann_args in annotations:
            if action == "mission" and ann_args:
                set_mission(session_id, ann_args[0])
                print(f"{LOG_PREFIX} Mission ← {ann_args[0]}")
            elif action == "fact" and len(ann_args) >= 2:
                add_fact(session_id, ann_args[0], ann_args[1])
                print(f"{LOG_PREFIX} Fact: {ann_args[0]} = {ann_args[1]}")
            elif action == "fact-" and ann_args:
                if remove_fact(session_id, ann_args[0]):
                    print(f"{LOG_PREFIX} Fact removed: {ann_args[0]}")
            elif action == "facts-clear":
                clear_facts(session_id)
                print(f"{LOG_PREFIX} All facts cleared")

    # ── Track last tool (EVERY tool) ───────────────────────────
    summary = _summarise_tool_args(tool_name, _a)
    set_last_tool(session_id, tool_name, summary)

    # ── SSH detection (terminal only) ──────────────────────────
    if tool_name != "terminal":
        return

    ssh_target = extract_ssh_target(command)
    if ssh_target:
        print(f"{LOG_PREFIX} SSH detected -> {ssh_target}")
        try:
            local = subprocess.run(
                ["hostname", "-s"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:
            local = "localhost"
        set_host(session_id, ssh_target, local_host=local)
        return

    if is_exit_command(command):
        print(f"{LOG_PREFIX} Exit detected -> resetting host")
        try:
            host = subprocess.run(
                ["hostname", "-s"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:
            host = "localhost"
        set_host(session_id, host, local_host=host)
        return

    # ── Task inference (debounced) ─────────────────────────────
    task = _infer_task(command)
    state = get_state(session_id)
    if _debounce_task_update(state, task):
        old_task = state.get("current_task", "")
        print(f"{LOG_PREFIX} Task: {old_task} -> {task}")
        set_task(session_id, task)
