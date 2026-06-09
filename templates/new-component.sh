#!/usr/bin/env bash
# astra 新组件脚手架
# 用法: templates/new-component.sh <type> <component-name>
#   type: skill | mcp | sre
#   component-name: kebab-case，如 astra-skill-my-thing

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "用法: $0 <type> <component-name>"
  echo "  type: skill | mcp | sre"
  echo "  component-name: kebab-case，如 astra-skill-my-thing"
  exit 1
fi

TYPE="$1"
NAME="$2"
BASE_DIR="$HOME/Projects/astra"

# 验证 type
case "$TYPE" in
  skill|mcp|sre) ;;
  *) echo "❌ 不支持的 type: $TYPE（可选: skill, mcp, sre）" >&2; exit 1 ;;
esac

# 目标目录
TARGET_DIR="$BASE_DIR/$NAME"

if [ -d "$TARGET_DIR" ]; then
  echo "❌ 目录已存在: $TARGET_DIR" >&2
  exit 1
fi

echo "🚀 创建 $TYPE 组件: $NAME"
echo "   路径: $TARGET_DIR"

# --- skill 模板 ---
if [ "$TYPE" = "skill" ]; then
  mkdir -p "$TARGET_DIR"

  cat > "$TARGET_DIR/SKILL.md" <<-EOF
	---
	description: ""
	tags: []
	triggers: []
	---

	# $NAME

	TODO: 在此填写 skill 描述、触发条件、执行步骤。

	## 触发条件

	- ...

	## 步骤

	1. ...
	EOF

  # 注册到 registry.yaml
  REGISTRY="$HOME/Projects/astra/astra-aiagent-infra/registry.yaml"
  if [ -f "$REGISTRY" ]; then
    # 在 skills 节的末尾插入
    # 用简单方式——在第二个 - type: sre 行前插入
    # 这里借助 Python 来做 YAML 友好的追加
    python3 -c "
import yaml
path = '$REGISTRY'
with open(path) as f:
    data = yaml.safe_load(f)
data['components'].append({
    'type': 'skill',
    'name': '$NAME',
    'repo': 'alrcatraz/$NAME',
    'description': 'TODO',
    'status': 'active',
    'location': '',
})
with open(path, 'w') as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
print('✅ 已追加到 registry.yaml')
" 2>/dev/null || echo "⚠️  请手动将 $NAME 追加到 registry.yaml"
  fi

# --- mcp 模板 ---
elif [ "$TYPE" = "mcp" ]; then
  mkdir -p "$TARGET_DIR/src/$NAME"
  mkdir -p "$TARGET_DIR/tests"

  cat > "$TARGET_DIR/pyproject.toml" <<-EOF
	[project]
	name = "$NAME"
	version = "0.1.0"
	description = "TODO"
	requires-python = ">=3.11"
	dependencies = [
	    "mcp",
	]

	[project.urls]
	repository = "https://github.com/alrcatraz/$NAME"
	EOF

  cat > "$TARGET_DIR/src/$NAME/__init__.py" <<-EOF
	"""$NAME — TODO"""
	__version__ = "0.1.0"
	EOF

  cat > "$TARGET_DIR/src/$NAME/server.py" <<-EOF
	"""MCP 服务入口"""
	import mcp.server.stdio
	import mcp.types as types
	from mcp.server import NotificationOptions, Server
	from mcp.server.models import InitializationOptions

	server = Server("$NAME")

	@server.list_tools()
	async def handle_list_tools() -> list[types.Tool]:
	    return []

	@server.call_tool()
	async def handle_call_tool(
	    name: str, arguments: dict
	) -> list[types.TextContent]:
	    raise ValueError(f"未知工具: {name}")

	async def main():
	    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
	        await server.run(
	            read_stream,
	            write_stream,
	            InitializationOptions(
	                server_name="$NAME",
	                server_version="0.1.0",
	            ),
	        )
	EOF

# --- sre 模板 ---
elif [ "$TYPE" = "sre" ]; then
  mkdir -p "$TARGET_DIR/scripts"
  mkdir -p "$TARGET_DIR/references"

  cat > "$TARGET_DIR/README.md" <<-EOF
	# $NAME

	TODO: SRE 模块描述。
	EOF
fi

echo "✅ 组件创建完成: $TARGET_DIR"
echo "   编辑文件后记得 git init && git add && git commit"
