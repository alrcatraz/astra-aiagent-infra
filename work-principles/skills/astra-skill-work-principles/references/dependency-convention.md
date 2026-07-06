# Astra 生态依赖关系标注约定

> 决策记录 (2026-06-18)
> - **场景:** 需要为 astra-aiagent-infra 生态的各公共存储库标注依赖关系，以便从任何入口发现库时都能了解其上下游。
> - **触发:** 预研 skill (pre-action-research) 引用了 `references/credential-yaml-schema.md`，该文件不在同一仓库中。

## 三层标注体系

每个 astra 生态的组件使用三层机制标注依赖：

```
层 1: meta-repo registry.yaml
    → 结构化数据，机器可解析
    → 字段: depends_on[{repo, resource, required, reason}]

层 2: 各 repo README.md Dependencies 表格
    → GitHub 首页可见，人类可读
    → 列: Repository / Resource / Required / Purpose

层 3: 各 repo AGENTS.md Dependencies 部分
    → Agent 加载时可见，运行时参考
    → 按 Runtime / Access / Ecosystem 分组
```

## required 级别

| 级别 | 含义 | 示例 |
|:----|:-----|:-----|
| `required` | 没有此依赖组件无法工作 | 上游 fork, runtime |
| `recommended` | 强烈建议安装，有它体验显著增强 | 共享 DB schema |
| `optional` | 特定场景才需要 | 凭据文档参考 |

## 适用场景

- 所有 astra-* 系列公共 GitHub 存储库
- 新增组件时，template 已内置 Dependencies 表格占位
- 依赖关系变更时，三层同步更新
