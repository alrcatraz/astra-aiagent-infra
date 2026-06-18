# Astra AI Agent Infrastructure (astra-aiagent-infra)

<div align="center">

[![License](https://badgen.net/github/license/alrcatraz/astra-aiagent-infra)](LICENSE)
[![GitHub stars](https://badgen.net/github/stars/alrcatraz/astra-aiagent-infra)](https://github.com/alrcatraz/astra-aiagent-infra)
[![GitHub last commit](https://badgen.net/github/last-commit/alrcatraz/astra-aiagent-infra)](https://github.com/alrcatraz/astra-aiagent-infra/commits)

</div>

> Hermes Agent ecosystem portal — Skills · SRE framework · MCP services · Tutorials
> Companion for *Hermes Agent Advanced Tutorial* Vol. III

---

## 🏛️ What Is This

This is not a traditional "code repository" — it is an **ecosystem portal**.

Open [`registry.yaml`](registry.yaml) to see an overview of everything built for Hermes Agent:

```yaml
tutorials: Hermes Agent from scratch (3 volumes)
skills:    Workflow enforcement skill set
sre:       Unified SRE coordination layer
mcps:      MCP extension services
```

Every component lives in its **own repository** with its own versioning and release cadence.

---

## 📋 Component Overview

| Category | Component | Repository | Depends On | Status |
|:---------|:----------|:-----------|:-----------|:------:|
| 🧭 Framework | execution-framework | `alrcatraz/astra-skill-execution-framework` | 4 sub-skills (optional) | 🟢 Active |
| 📘 Tutorial | Hermes Agent Tutorial (3 vols) | `alrcatraz/hermes-agent-tutorial` | — | 🟡 Planning |
| 🔧 Skill | pre-action-research | `alrcatraz/astra-skill-pre-action-research` | astra-aiagent-infra (optional) | 🟢 Active |
| 🔧 Skill | change-safeguard | `alrcatraz/astra-skill-change-safeguard` | — | 🟢 Active |
| 🔧 Skill | deploy-register | `alrcatraz/astra-skill-deploy-register` | — | 🟢 Active |
| 🔧 Skill | work-closure-check | `alrcatraz/astra-skill-work-closure-check` | astra-sre, astra-aiagent-infra | 🟢 Active |
| 🛡️ SRE | astra-sre coordination layer | `alrcatraz/astra-sre` | astra-knowledge-base-mcp (recommended) | 🟢 Active |
| 🔌 MCP | astra-knowledge-base | `alrcatraz/astra-knowledge-base-mcp` | — | 🟢 Active |
| 🖥️ Infra | astra-camofox-browser | `alrcatraz/astra-camofox-browser` (astra branch) | — | 🟢 Active |

> Full details (descriptions, transport types, `depends_on` reasons) → [`registry.yaml`](registry.yaml)

---

## 🚀 Getting Started

### Want to use a skill?

```bash
# Clone from the component's own repository
git clone https://github.com/alrcatraz/astra-skill-change-safeguard.git
cp -r astra-skill-change-safeguard ~/.hermes/skills/change-safeguard
```

### Want to use an MCP service?

Each component's README contains detailed installation and configuration instructions.

### Want to follow the tutorial?

Watch [`alrcatraz/hermes-agent-tutorial`](https://github.com/alrcatraz/hermes-agent-tutorial) (coming soon).

---

## 🧭 Directory Structure

```
astra-aiagent-infra/
├── registry.yaml            ← ☝️ Core entry: ecosystem overview
├── mcp/                     ← MCP design documents
├── templates/               ← Scaffolding templates for new components
├── docs/                    ← Cross-component design standards & guides
├── .gitignore
└── LICENSE
```

---

## License

MIT © 2026 Nanaly

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-aiagent-infra,alrcatraz/astra-skill-execution-framework,alrcatraz/astra-skill-change-safeguard,alrcatraz/astra-skill-deploy-register,alrcatraz/astra-skill-pre-action-research,alrcatraz/astra-skill-work-closure-check,alrcatraz/astra-sre,alrcatraz/astra-camofox-browser,alrcatraz/hermes-agent-tutorial,alrcatraz/astra-knowledge-base-mcp&type=date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-aiagent-infra,alrcatraz/astra-skill-execution-framework,alrcatraz/astra-skill-change-safeguard,alrcatraz/astra-skill-deploy-register,alrcatraz/astra-skill-pre-action-research,alrcatraz/astra-skill-work-closure-check,alrcatraz/astra-sre,alrcatraz/astra-camofox-browser,alrcatraz/hermes-agent-tutorial,alrcatraz/astra-knowledge-base-mcp&type=date" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=alrcatraz/astra-aiagent-infra,alrcatraz/astra-skill-execution-framework,alrcatraz/astra-skill-change-safeguard,alrcatraz/astra-skill-deploy-register,alrcatraz/astra-skill-pre-action-research,alrcatraz/astra-skill-work-closure-check,alrcatraz/astra-sre,alrcatraz/astra-camofox-browser,alrcatraz/hermes-agent-tutorial,alrcatraz/astra-knowledge-base-mcp&type=date" width="600" />
  </picture>
</div>

---

## 中文版

### 这是什么

这不是传统意义上的"代码仓库"——它是一个**生态门户**。

打开 [`registry.yaml`](registry.yaml) 可以查看为 Hermes Agent 构建的所有组件概览。每个组件都拥有**独立的仓库**，独立版本管理和发布节奏。

### 组件一览

| 类别 | 组件 | 仓库 | 依赖 | 状态 |
|:-----|:------|:-----|:----|:----:|
| 🧭 框架 | execution-framework | `alrcatraz/astra-skill-execution-framework` | 4 子 skill（可选） | 🟢 活跃 |
| 📘 教程 | Hermes Agent 教程（三卷） | `alrcatraz/hermes-agent-tutorial` | — | 🟡 规划中 |
| 🔧 Skill | pre-action-research | `alrcatraz/astra-skill-pre-action-research` | astra-aiagent-infra（可选） | 🟢 活跃 |
| 🔧 Skill | change-safeguard | `alrcatraz/astra-skill-change-safeguard` | — | 🟢 活跃 |
| 🔧 Skill | deploy-register | `alrcatraz/astra-skill-deploy-register` | — | 🟢 活跃 |
| 🔧 Skill | work-closure-check | `alrcatraz/astra-skill-work-closure-check` | astra-sre, astra-aiagent-infra | 🟢 活跃 |
| 🛡️ SRE | astra-sre 协调层 | `alrcatraz/astra-sre` | astra-knowledge-base-mcp（推荐） | 🟢 活跃 |
| 🔌 MCP | astra-knowledge-base | `alrcatraz/astra-knowledge-base-mcp` | — | 🟢 活跃 |
| 🖥️ 基础 | astra-camofox-browser | `alrcatraz/astra-camofox-browser`（astra 分支） | — | 🟢 活跃 |
