#!/bin/bash
# astra-sre-refresh.sh — 每月维护任务
# 1. 检查 Hermes 版本是否有更新
# 2. 运行 learn.py 检查新重复模式
# 3. 只在有变化时输出（no_agent 模式静默）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LEARN_PY="$SCRIPT_DIR/learn.py"
ENV_FILE="$HOME/.hermes/.env"
HERMES_VERSION_FILE="$HOME/.hermes/.version"
REPORT=""

# ── 检查 Hermes 版本 ─────────────────────────────────────────
if command -v hermes &>/dev/null; then
    CURRENT_VER=$(hermes --version 2>/dev/null | head -1 || echo "unknown")
    if [ -f "$HERMES_VERSION_FILE" ]; then
        LAST_VER=$(cat "$HERMES_VERSION_FILE")
    else
        LAST_VER="unknown"
    fi

    if [ "$CURRENT_VER" != "$LAST_VER" ]; then
        REPORT+="📦 Hermes 版本变更: $LAST_VER → $CURRENT_VER"$'\n'
        REPORT+="   请检查 dynamic_ref 中的 Gateway 消息长度限制是否需要更新"$'\n'
        echo "$CURRENT_VER" > "$HERMES_VERSION_FILE"
    fi
fi

# ── 运行 learn.py 检查新模式 ─────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

LEARN_OUTPUT=$(cd "$SCRIPT_DIR" && uv run --with psycopg2-binary python3 "$LEARN_PY" --cron 2>&1) || true
if [ -n "$LEARN_OUTPUT" ]; then
    REPORT+="$LEARN_OUTPUT"$'\n'
fi

# ── 输出 ─────────────────────────────────────────────────────
if [ -n "$REPORT" ]; then
    echo "$REPORT"
fi
exit 0
