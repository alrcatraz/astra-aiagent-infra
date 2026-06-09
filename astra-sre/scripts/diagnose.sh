#!/bin/bash
# astra-sre diagnose.sh — Phase 2-⑥ 子代理并行排查框架（入口）
# Wraps diagnose.py with env sourcing and uv dependency handling.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIAGNOSE_PY="$SCRIPT_DIR/diagnose.py"

# Source env for DB password
ENV_FILE="$HOME/.hermes/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# Run with uv (auto-installs psycopg2-binary if needed)
exec uv run --with psycopg2-binary python3 "$DIAGNOSE_PY" "$@"
