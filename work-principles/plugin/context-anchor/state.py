"""Per-session state management for context-anchor plugin.

Every session has its own independent row in the database backend.
No global/shared fields — zero cross-session contamination.

Backend is selected automatically via CONTEXT_ANCHOR_DATABASE_URL:
  postgresql://...  → PostgreSQL
  sqlite:///...     → SQLite at path
  unset             → SQLite at ~/.hermes/persistent/context-anchor.db
"""

from .backend import get_backend, close_backend


# ── Default state for a fresh session ──────────────────────────────

def _default_state(session_id: str) -> dict:
    """Return a clean state dict for a brand-new session."""
    import subprocess
    host = "localhost"
    try:
        host = subprocess.run(
            ["hostname", "-s"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or "localhost"
    except Exception:
        pass
    return {
        "session_id": session_id,
        "current_host": host,
        "local_host": host,
        "current_mission": "",
        "current_task": "awaiting-user-input",
        "last_tool": "",
        "key_facts": {},
    }


# ── Session-scoped helpers ─────────────────────────────────────────


def _load_or_default(session_id: str) -> dict:
    """Load state for *session_id*, or create a fresh default."""
    backend = get_backend()
    state = backend.load(session_id)
    if state is None:
        state = _default_state(session_id)
    return state


def _save(session_id: str, state: dict):
    """Persist state for *session_id* via the active backend."""
    backend = get_backend()
    backend.save(session_id, state)


# ── Public API ─────────────────────────────────────────────────────


def get_state(session_id: str | None = None) -> dict:
    """Return state for the given session.

    If session_id is None, returns an empty template (for contexts
    where the session id is not yet known — callers should always
    prefer passing a session_id).
    """
    if session_id is None:
        return _default_state("")
    return _load_or_default(session_id)


def set_host(session_id: str, host: str, local_host: str | None = None):
    """Update the current and (optionally) local hostname."""
    state = _load_or_default(session_id)
    state["current_host"] = host
    if local_host is not None:
        state["local_host"] = local_host
    _save(session_id, state)


def set_task(session_id: str, task: str):
    """Update the current task label."""
    state = _load_or_default(session_id)
    state["current_task"] = task
    _save(session_id, state)


def set_mission(session_id: str, mission: str):
    """Update the session-level mission."""
    state = _load_or_default(session_id)
    state["current_mission"] = mission
    _save(session_id, state)


def set_last_tool(session_id: str, tool_name: str, summary: str = ""):
    """Record the most recently called tool."""
    state = _load_or_default(session_id)
    parts = [tool_name]
    if summary:
        parts.append(summary[:60])
    state["last_tool"] = ": ".join(parts)
    _save(session_id, state)


def add_fact(session_id: str, key: str, value: str):
    """Store a key fact (scoped to this session)."""
    state = _load_or_default(session_id)
    facts = state.setdefault("key_facts", {})
    facts[key] = value
    # Hard cap per session
    if len(facts) > 20:
        oldest = sorted(facts.keys())[: len(facts) - 20]
        for k in oldest:
            del facts[k]
    _save(session_id, state)


def remove_fact(session_id: str, key: str) -> bool:
    """Remove a fact by key. Returns True if it existed."""
    state = _load_or_default(session_id)
    facts = state.setdefault("key_facts", {})
    existed = key in facts
    facts.pop(key, None)
    if existed:
        _save(session_id, state)
    return existed


def clear_facts(session_id: str):
    """Clear all facts for this session."""
    state = _load_or_default(session_id)
    state["key_facts"] = {}
    _save(session_id, state)


def record_session(session_id: str, local_hostname: str | None = None):
    """Ensure a session row exists, resetting transient fields if new.

    This is called once per session at first tool invocation.
    The session row is created (with defaults) if absent.
    """
    backend = get_backend()
    existing = backend.load(session_id)

    if existing is not None:
        # Session already has state — nothing to reset
        return

    # Fresh session: create default row
    import subprocess
    host = local_hostname or "localhost"
    if not local_hostname:
        try:
            host = subprocess.run(
                ["hostname", "-s"], capture_output=True, text=True, timeout=5
            ).stdout.strip() or "localhost"
        except Exception:
            pass

    state = {
        "session_id": session_id,
        "current_host": host,
        "local_host": host,
        "current_mission": "",
        "current_task": "awaiting-user-input",
        "last_tool": "",
        "key_facts": {},
    }
    backend.save(session_id, state)
    print(f"[context-anchor] New session {session_id[:12]}... created")


# ── SSH helpers (no session_id needed — pure parsing) ──────────────


def extract_ssh_target(command: str) -> str | None:
    """Parse 'ssh user@host' or 'ssh host' from a command string.

    Handles -p PORT, -o OPTION, -J HOP, -l USER flag pairs correctly
    so the port number is never mistaken for a hostname.
    """
    import shlex
    parts = shlex.split(command)
    if not parts or parts[0] not in ("ssh", "ssh.exe", "sshpass"):
        return None
    _ARG_FLAGS = frozenset({
        "-p", "-o", "-J", "-l", "-b", "-i", "-F",
        "-E", "-c", "-m", "-O", "-S", "-w", "-D", "-L", "-R",
    })
    skip_next = False
    for p in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if p in _ARG_FLAGS:
            skip_next = True
            continue
        if p.startswith("-"):
            continue
        if "=" in p and not p.startswith("-"):
            continue
        host = p.split("@")[-1] if "@" in p else p
        return host.split(":")[0]
    return None


def is_exit_command(command: str) -> bool:
    parts = command.strip().split()
    return bool(parts) and parts[0] in ("exit", "logout", "quit")


# ── Anchor annotations ─────────────────────────────────────────────

# Patterns parsed from terminal commands by the hook:
#   #anchor:mission <text>           → set mission
#   #anchor:fact <key>=<value>       → add fact
#   #anchor:fact- <key>              → remove fact
#   #anchor:facts-clear              → clear all facts


def parse_anchor_annotations(command: str) -> list[tuple[str, list[str]]]:
    """Extract anchor annotations from a command string.

    Returns list of (action, args) tuples:
      ("mission", ["deploy to office devices"])
      ("fact", ["zt_nuc10", "0723939b24"])
      ("fact-", ["zt_nuc10"])
      ("facts-clear", [])
    """
    results = []
    import re
    for m in re.finditer(r"#anchor:(\S+)(?:\s+(.*?))?(?:\s*#|$)", command):
        action = m.group(1)
        rest = (m.group(2) or "").strip()
        if action == "mission":
            if rest:
                results.append(("mission", [rest]))
        elif action == "fact":
            if "=" in rest:
                key, value = rest.split("=", 1)
                results.append(("fact", [key.strip(), value.strip()]))
        elif action == "fact-":
            if rest:
                results.append(("fact-", [rest.strip()]))
        elif action == "facts-clear":
            results.append(("facts-clear", []))
    return results


# ── Teardown ───────────────────────────────────────────────────────

def teardown():
    """Release backend resources."""
    close_backend()
