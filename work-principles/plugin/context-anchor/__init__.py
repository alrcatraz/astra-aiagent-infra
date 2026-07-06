"""Context-anchor plugin — main entry point.

Registers pre_response and post_tool_call hooks with Hermes plugin system."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire hooks into Hermes lifecycle.

    Args:
        ctx: Plugin context with register_hook(), register_tool(), etc.
    """
    try:
        from .hooks import on_pre_llm_call, on_post_tool_call

        ctx.register_hook("pre_llm_call", on_pre_llm_call)
        ctx.register_hook("post_tool_call", on_post_tool_call)

        logger.info("context-anchor: registered pre_llm_call + post_tool_call hooks")
    except Exception as e:
        logger.error("context-anchor: failed to register hooks: %s", e)
