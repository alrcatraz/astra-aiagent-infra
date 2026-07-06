# Astra 生态版本号约定（速查）

> 完整规范：`astra-aiagent-infra-template/VERSIONING.md`
> 验证工具：`execution-framework/scripts/sync-routing.py --verify-versions`

## 格式

SemVer 2.0.0 的 `+build` 后缀：

| 场景 | 格式 | 示例 |
|:-----|:-----|:-----|
| 正式发布 | `X.Y.Z` + `git tag vX.Y.Z` | `v2.0.0` |
| 本地微调（无 tag） | `X.Y.Z+local.N` | `2.0.0+local.1` |
| 他人 Fork 修改 | `X.Y.Z+forker.N` | `2.0.0+lilei.1` |
| registry.yaml | 仅 `X.Y.Z`（无后缀） | `2.0.0` |

## 为什么用 `+` 而不是 `-`

- `1.0.0-nanaly.1` → 预发布语义，version < `1.0.0`（错误）
- `1.0.0+nanaly.1` → 构建元数据，version == `1.0.0`（正确）

## 版本存在位置

| 仓库类型 | 文件 | 字段 |
|:---------|:-----|:-----|
| astra-skill-* | SKILL.md frontmatter | `version:` |
| astra-sre 等含 Python 的项目 | pyproject.toml | `[project] version =` |
| astra-aiagent-infra | registry.yaml | `version:` (clean only) |

## 生命周期

```
Tag v1.0.0 → SKILL.md = 1.0.0, registry = 1.0.0
   ↓
本地修改 → SKILL.md = 1.0.0+local.1 (无 tag, 无 registry 更新)
   ↓
正式发布 → v1.1.0 → 所有后缀清空 → SKILL.md = 1.1.0, registry = 1.1.0
```

## 验证

```bash
cd <path-to-execution-framework>
uv run scripts/sync-routing.py --verify-versions
```

如果 `registry.yaml` 里 `version: 1.0.0` 但本地的 `pyproject.toml` 还是 `0.1.0`，会被标记为 `❌ DRIFT`。在 commit 前跑这个检查，一次性捕获所有版本不对齐的仓库。
