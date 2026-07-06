"""Context-anchor hooks for Hermes plugin system.

on_pre_llm_call:   Injects [AGENT CONTEXT] header into system prompt before each LLM call.
on_post_tool_call: Detects SSH enter/exit and auto-updates current_host in state.json.

NOTE: Uses relative imports within the plugin package (Hermes loads via importlib)."""

from .state import get_state, set_host, record_session, extract_ssh_target, is_exit_command
import subprocess

LOG_PREFIX = "[context-anchor]"


def on_pre_llm_call(*args, **kwargs) -> str:
    """Inject [AGENT CONTEXT] header before every LLM call.
    Hermes passes system_prompt as the first positional argument.
    Returns modified system_prompt (first arg) if available."""
    state = get_state()
    host = state.get("current_host", "unknown")
    task = state.get("current_task", "awaiting-user-input")
    thread_ids = state.get("thread_session_ids", [])
    thread_hint = ""
    if thread_ids:
        last_id = thread_ids[-1]
        thread_hint = f"\n[THREAD HISTORY] {len(thread_ids)} session(s) in this thread. Last: {last_id}"

    header = f"\n[AGENT CONTEXT] host={host} | task={task}{thread_hint}\n"
    
    # Return modified system_prompt if provided, otherwise just return header
    if args:
        system_prompt = args[0]
        return header + system_prompt
    system_prompt = kwargs.get("system_prompt", "")
    return header + system_prompt


def on_post_tool_call(result: dict, session_id: str = None, **kwargs):
    """Auto-detect SSH and update state."""
    command = result.get("command", "")
    if not command:
        return

    # Record session_id in thread history
    if session_id:
        record_session(session_id)

    # SSH enter
    ssh_target = extract_ssh_target(command)
    if ssh_target:
        print(f"{LOG_PREFIX} SSH detected -> {ssh_target}")
        set_host(ssh_target)
        return

    # SSH exit
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
