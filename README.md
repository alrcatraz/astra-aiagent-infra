# Astra AI Agent Infrastructure (astra-aiagent-infra)

> Hermes Agent 生态门户 — 技能 · 运维框架 · MCP 服务 · 教程  
> 配套《Hermes Agent 进阶教程》卷三使用

---

## 🏛️ 这是什么

这不是一个传统的"代码仓库"——它是一个**生态门户**。

打开 [`registry.yaml`](registry.yaml)，你就能一览我为 Hermes Agent 构建的所有成果：

```yaml
# 一个文件 = 整个生态的全景
tutorials: 从零开始的 Hermes Agent 教程
skills:    流程保障技能集
sre:       统一运维协调层
mcps:      MCP 扩展服务
```

每个组件都在**独立的仓库**中维护，有自己的版本迭代节奏。

---

## 📋 组件一览

| 类别 | 组件 | 独立仓库 | 状态 |
|:-----|:-----|:---------|:----:|
| 📘 教程 | Hermes Agent 教程（三卷） | `alrcatraz/hermes-agent-tutorial` | 🟢 规划中 |
| 🔧 技能 | pre-action-research | `alrcatraz/astra-skill-pre-action-research` | 🟢 活动 |
| 🔧 技能 | change-safeguard | `alrcatraz/astra-skill-change-safeguard` | 🟢 活动 |
| 🔧 技能 | deploy-register | `alrcatraz/astra-skill-deploy-register` | 🟢 活动 |
| 🔧 技能 | work-closure-check | `alrcatraz/astra-skill-work-closure-check` | 🟢 活动 |
| 🛡️ SRE | astra-sre 协调层 | `alrcatraz/astra-sre` | 🟢 活动 |
| 🔌 MCP | astra-knowledge-base | `alrcatraz/astra-knowledge-base-mcp` | 🟢 活动 |
| 🔌 MCP | astra-time | 内置 (Hermes) | 🟢 活动 |
| 🔌 MCP | astra-markitdown | 内置 (Hermes) | 🟢 活动 |

> 完整信息（含描述、transport 类型等）→ [`registry.yaml`](registry.yaml)

---

## 🚀 开始使用

### 想用某套技能？

```bash
# 复制想要的 skill 到你的 Hermes 目录
cp -r skills/change-safeguard ~/.hermes/skills/
# 或从独立仓库拉取
git clone https://github.com/alrcatraz/astra-skill-change-safeguard.git
```

### 想用 MCP 服务？

对应独立仓库的 README 中有详细的安装和配置说明。

### 想跟着教程学？

请关注 [`alrcatraz/hermes-agent-tutorial`](https://github.com/alrcatraz/hermes-agent-tutorial)（即将发布）。

---

## 🧭 目录结构

```
astra-aiagent-infra/
├── registry.yaml            ← ☝️ 核心入口：生态全景图
├── skills/                  ← 技能代码（待提取独立仓库）
├── astra-sre/               ← SRE 模块代码（待提取独立仓库）
├── mcp/                     ← MCP 设计文档
├── templates/               ← 新建组件的脚手架模板
├── docs/                    ← 跨组件的设计规范与指南
├── .gitignore
└── LICENSE
```

---

## 🤝 许可证

MIT © 2026 Nanaly
