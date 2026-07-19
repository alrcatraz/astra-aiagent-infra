"""work-principles plugin: entry point.

Registers:
  - ``discipline_set_phase`` tool — agent declares phase transitions
  - ``pre_llm_call`` hook — injects phase context every turn
  - ``pre_tool_call`` hook — blocks out-of-phase tool use
  - ``post_tool_call`` hook — [HARNESS:] markers, auto-loading, transitions
  - ``on_session_start`` hook — resets on new session
  - 5 bundled skills (namespaced ``work-principles:*``)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("work-principles")

# Plugin lives under work-principles/plugin/discipline/, resolve skills/
PLUGIN_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = PLUGIN_DIR / "skills"


def register(ctx) -> None:
    """Plugin registration — called once at Hermes startup."""
    from .hooks import on_pre_llm_call, on_pre_tool_call, on_post_tool_call, on_session_start
    from .state import Phase, set_phase

    _register_set_phase_tool(ctx)

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("on_session_start", on_session_start)

    _register_bundled_skills(ctx)

    logger.info("work-principles ready — tool + 4 hooks + 5 skills")


# ═══════════════════════════════════════════════════════════════════════
#  Tool
# ═══════════════════════════════════════════════════════════════════════

def _register_set_phase_tool(ctx) -> None:
    from .state import Phase, set_phase

    phases = [p.value for p in Phase]
    schema = {
        "name": "discipline_set_phase",
        "description": (
            "Declare the current work phase. Call this when transitioning "
            "between phases so the plugin provides phase-appropriate "
            f"guidelines. Valid phases: {phases}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": phases,
                    "description": (
                        "New phase.\n"
                        "no_task=idle / casual conversation\n"
                        "task_started=new task; research gate active\n"
                        "planning=research done; propose plan; wait for approval\n"
                        "accessing_device=need device credentials (transient)\n"
                        "executing=running the approved plan\n"
                        "modifying=about to modify files/config (transient)\n"
                        "closing=task complete; run closure checks"
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Why this transition. E.g. 'need to SSH into VPS-HK' "
                        "or 'adding auth middleware'"
                    ),
                },
            },
            "required": ["phase", "reason"],
        },
    }

    def handle(params: dict, **kwargs) -> str:
        phase_name = params.get("phase")
        reason = params.get("reason", "")
        try:
            phase = Phase(phase_name)
        except ValueError:
            return json.dumps({
                "success": False,
                "error": f"Invalid phase '{phase_name}'. Valid: {phases}",
            })

        session_id = os.environ.get("HERMES_SESSION_ID") or kwargs.get("session_id")
        new_state = set_phase(phase, reason, session_id=session_id)

        msg = f"Phase set to: {phase.value}"
        if reason:
            msg += f"  (reason: {reason})"

        prev = new_state.get("previous_phase")
        if prev:
            msg += f"  (will return to: {prev} when done)"

        logger.info("phase→%s — %s", phase.value, reason)
        return json.dumps({
            "success": True,
            "message": msg,
            "state": new_state,
        }, ensure_ascii=False)

    ctx.register_tool(
        name="discipline_set_phase",
        toolset="work_principles",
        schema=schema,
        handler=handle,
        description="Declare current work phase for discipline guidance",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Bundled skills  (symlinks -> ~/.hermes/skills/devops/<name>/)
# ═══════════════════════════════════════════════════════════════════════

_BUNDLED_SKILLS: list[tuple[str, Path]] = [
    ("work-principles", SKILLS_DIR / "work-principles" / "SKILL.md"),
    ("pre-action-research", SKILLS_DIR / "pre-action-research" / "SKILL.md"),
    ("change-safeguard", SKILLS_DIR / "change-safeguard" / "SKILL.md"),
    ("work-closure-check", SKILLS_DIR / "work-closure-check" / "SKILL.md"),
    ("credential-store-management", SKILLS_DIR / "credential-store-management" / "SKILL.md"),
]


def _register_bundled_skills(ctx) -> None:
    for name, path in _BUNDLED_SKILLS:
        if path.exists():
            ctx.register_skill(name, path)
            logger.info("  skill registered: work-principles:%s", name)
        else:
            logger.warning("  skill MISSING: %s", path)
