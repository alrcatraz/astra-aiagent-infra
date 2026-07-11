"""Context-anchor hooks for Hermes plugin system.

on_pre_llm_call:   Injects [AGENT CONTEXT] header into system prompt before each LLM call.
on_post_tool_call: Detects SSH enter/exit, records session IDs, and infers task context
                   from any terminal command via generative verb:subject extraction
                   (no fixed category list — covers everything).

NOTE: Uses relative imports within the plugin package (Hermes loads via importlib)."""

from .state import get_state, set_host, record_session, set_task, extract_ssh_target, is_exit_command
import subprocess
import shlex
from datetime import datetime, timezone

LOG_PREFIX = "[context-anchor]"

# Tokens to strip from the start of commands before extracting verb
_COMMAND_PREFIXES = frozenset({"sudo", "time", "nohup", "setsid", "env", "noglob", "doas"})
# Commands whose subject is the SSH target host
_SSH_LIKE = frozenset({"ssh", "sshpass", "scp", "rsync", "sftp"})


def _infer_task(command: str) -> str:
    """Extract a descriptive 'verb:subject' from any terminal command.

    Always returns a string — no categories, no gaps, no exhaustive list to maintain.
    Examples::

        ssh -p 2222 root@100.64.0.1          → "ssh:100.64.0.1"
        grep dm_topic ~/.hermes/logs/log     → "grep:gateway.log"
        emerge -uDN @world                   → "emerge:world"
        cat /etc/sysctl.conf                 → "cat:sysctl.conf"
        python3 scripts/test.py              → "python3:test.py"
        curl https://api.example.com/v1      → "curl:api.example.com"
        nmcli connection show                → "nmcli:connection"
        docker ps --all                      → "docker:ps"
        journalctl -u sshd --no-pager        → "journalctl:sshd"
        dmesg | grep error                   → "dmesg:error"
        ls -la /etc/ssh/                     → "ls:ssh"
        cd ~/Projects/astra/                 → "cd:astra"
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return "noop"

    # Strip leading prefix noise
    while tokens and tokens[0] in _COMMAND_PREFIXES:
        tokens.pop(0)
    if not tokens:
        return "noop"

    verb = tokens[0]

    # --- SSH-like: extract target host (skip flags, strip user@ and port) ---
    if verb in _SSH_LIKE:
        for t in tokens[1:]:
            if not t.startswith("-") and "=" not in t:
                target = t.split("@")[-1].split(":")[0]
                return f"ssh:{target}"
        return "ssh"

    # --- Pipe chains: find the pipe position, search for subject only before it ---
    pipe_at = None
    for i, t in enumerate(tokens):
        if t == "|":
            pipe_at = i
            break

    search_until = pipe_at if pipe_at is not None else len(tokens)

    # --- Generic: find first non-flag positional arg as subject ---
    for t in tokens[1:search_until]:
        if t.startswith("-"):
            continue
        if t in {">", ">>", "<", "2>", "&>", "|", ";", "&&", "||"}:
            continue
        subject = _shorten_subject(t)
        return f"{verb}:{subject}"

    # --- No subject found — just the verb ---
    return verb


def _shorten_subject(s: str) -> str:
    """Shorten a subject to its most identifiable fragment."""
    # URL: keep hostname
    if s.startswith(("http://", "https://")):
        # https://host/path → extract host
        after_slashes = s.split("//", 1)[-1] if "//" in s else s
        host = after_slashes.split("/")[0].split(":")[0]  # strip port too
        return host
    # Path: last component (basename)
    if "/" in s:
        base = s.rstrip("/").split("/")[-1]
        if len(base) > 35:
            base = base[:32] + "..."
        return base
    # Quoted multi-word: first word only
    if " " in s and not s.startswith(("'", '"')):
        return s.split()[0]
    # Truncate extreme length
    if len(s) > 35:
        return s[:32] + "..."
    return s


def _debounce_task_update(state: dict, new_task: str) -> bool:
    """Return True if current_task should be updated.

    Prevents flip-flopping: only allow a task change if:
    - The task is actually different from current
    - More than 5 minutes have passed since last state update
    - OR the current task is the stale default "awaiting-user-input" / "testing"
    """
    current_task = state.get("current_task", "")
    if current_task == new_task:
        return False

    # Always replace stale/noop defaults immediately
    if current_task in ("awaiting-user-input", "testing", ""):
        return True

    # Otherwise debounce: wait 5 min between task changes
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


def on_pre_llm_call(*args, **kwargs) -> str:
    """Inject [AGENT CONTEXT] header before every LLM call.

    Hermes passes system_prompt as the first positional argument.
    Returns modified system_prompt (first arg) if available.
    """
    state = get_state()
    host = state.get("current_host", "unknown")
    task = state.get("current_task", "awaiting-user-input")
    thread_ids = state.get("thread_session_ids", [])
    thread_hint = ""
    if thread_ids:
        last_id = thread_ids[-1]
        thread_hint = (
            f"\n[THREAD HISTORY] {len(thread_ids)} session(s)"
            f" in this thread. Last: {last_id}"
        )

    header = f"\n[AGENT CONTEXT] host={host} | task={task}{thread_hint}\n"

    # Return modified system_prompt if the positional arg is provided
    if args:
        return header + args[0]
    # Fallback — kwargs (unlikely but keep for safety)
    system_prompt = kwargs.get("system_prompt", "")
    return header + system_prompt


def on_post_tool_call(tool_name: str, args: dict | None = None, result: str = None, **kwargs):
    """Auto-detect SSH, record session IDs, and infer task context.

    Called by Hermes after EVERY tool invocation. The session_id parameter
    is provided by the plugin framework for sessions that have one.

    Hermes post_tool_call signature:
      (tool_name, args, result, task_id, duration_ms)
    Prior code assumed the first positional was "result" which was actually
    tool_name — using args or result below for the command string.
    """
    # ALWAYS record session_id first — before the early return for
    # non-terminal tool results. This was the root cause of the
    # empty thread_session_ids bug.
    if session_id := kwargs.get("session_id"):
        record_session(session_id)

    # Extract command: try args dict first (it carries the actual params),
    # fall back to result string (for terminals without structured args).
    _a = args if isinstance(args, dict) else {}
    command = _a.get("command", "") or (result or "")
    if not command:
        # Non-terminal tool (read_file, web_search, session_search…)
        return

    # SSH enter — detect ssh user@host or ssh host
    ssh_target = extract_ssh_target(command)
    if ssh_target:
        print(f"{LOG_PREFIX} SSH detected -> {ssh_target}")
        set_host(ssh_target)
        return

    # SSH exit — detect exit / logout / quit
    if is_exit_command(command):
        print(f"{LOG_PREFIX} Exit detected -> resetting host")
        try:
            host = subprocess.run(
                ["hostname", "-s"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:
            host = "localhost"
        set_host(host)
        return

    # Task inference from terminal command keywords
    task = _infer_task(command)
    state = get_state()
    if _debounce_task_update(state, task):
        old_task = state.get("current_task", "")
        print(f"{LOG_PREFIX} Task: {old_task} -> {task}")
        set_task(task)
