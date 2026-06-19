# Astra AI Agent Infrastructure (astra-aiagent-infra)

<div align="center">

[![License](https://badgen.net/github/license/alrcatraz/astra-aiagent-infra)](LICENSE)
[![GitHub stars](https://badgen.net/github/stars/alrcatraz/astra-aiagent-infra)](https://github.com/alrcatraz/astra-aiagent-infra)
[![GitHub last commit](https://badgen.net/github/last-commit/alrcatraz/astra-aiagent-infra)](https://github.com/alrcatraz/astra-aiagent-infra/commits)
[![Sponsor](https://img.shields.io/github/sponsors/alrcatraz?label=Sponsor&logo=github&color=ea4aaa&logoColor=white)](https://github.com/sponsors/alrcatraz)

</div>

> Hermes Agent ecosystem portal — Skills · SRE framework · MCP services · Tutorials
> Companion for *Hermes Agent Advanced Tutorial* Vol. III

---

## 🏛️ What Is This

This is not a traditional "code repository" — it is an **ecosystem portal**.
Open [`registry.yaml`](registry.yaml) for the full overview; each component below lives in its own repository with independent versioning.

This repository also hosts:
- **`skills/devops/astra-hub/`** — The ecosystem map index (the document you are reading now, as a Hermes skill)
- **`lifecycle/astra-lifecycle-sync.py`** — Lifecycle hook syncing tool for the ecosystem

---

## 🚀 Quick Start

The ecosystem is built around a few core components. Start with what you need.

### Bare minimum — just the workflow enforcement skills

These five skills enforce safe, systematic task execution for any Hermes Agent workflow:

| Skill | What it does |
|:------|:-------------|
| **execution-framework** | Routes incoming tasks to the correct workflow |
| **pre-action-research** | Ensures you research before acting |
| **change-safeguard** | Backs up state and verifies after every change |
| **deploy-register** | Registers every deployed service |
| **work-closure-check** | Closes tasks cleanly with user confirmation |

```bash
# Install any skill in one command:
git clone https://github.com/alrcatraz/astra-skill-change-safeguard.git
cp -r astra-skill-change-safeguard ~/.hermes/skills/
```

### Add monitoring — include the SRE layer

| Component | What it does |
|:----------|:-------------|
| **astra-sre** | Unified SRE coordination — automated health scans, fault diagnosis, self-healing |
| **astra-knowledge-base-mcp** | Persistent memory: stores incident records, config snapshots, and dynamic references |

### Want the full picture?

Load the **astra-hub** skill (bundled in this repository's `skills/` directory) for a complete ecosystem map — project index, credential guide, maintenance schedules, and expert pitfalls.

---

## 📦 Component Overview

Each component has its own GitHub repository with its own releases and documentation.

### 🧭 execution-framework

A task classifier and workflow router. When any task arrives, the framework determines its type (research / modify / deploy / close), loads the matching skill, and guides execution step by step. Self-evolving: it auto-detects new skills and suggests routing table updates.

[![astra-skill-execution-framework](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-skill-execution-framework)](https://github.com/alrcatraz/astra-skill-execution-framework)

### 🔍 pre-action-research

Ensures every action is preceded by thorough research — project documentation, current system state, credential locations, and environmental constraints. Prevents guesswork and reduces rollback frequency.

[![astra-skill-pre-action-research](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-skill-pre-action-research)](https://github.com/alrcatraz/astra-skill-pre-action-research)

### 🛡️ change-safeguard

Before any modification — backup state, record environment baselines, plan rollback. After the change — verify functionality, scan for side-effects, clean up residuals. Turns every system change into a safe, auditable operation.

[![astra-skill-change-safeguard](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-skill-change-safeguard)](https://github.com/alrcatraz/astra-skill-change-safeguard)

### 📦 deploy-register

Every deployed service is registered immediately: inventory entry, health check configuration, and decommissioning procedure. Prevents "management black holes" — services running without oversight.

[![astra-skill-deploy-register](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-skill-deploy-register)](https://github.com/alrcatraz/astra-skill-deploy-register)

### 🎯 work-closure-check

Closes every task with discipline: confirm success with the user, clean up temporary files, save learned lessons as skills, update stale references, and deliver a concise completion summary.

[![astra-skill-work-closure-check](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-skill-work-closure-check)](https://github.com/alrcatraz/astra-skill-work-closure-check)

### 🛡️ astra-sre

A unified Site Reliability Engineering layer for Hermes Agent infrastructure. Automates health scanning across the fleet, diagnoses common failure modes (E2EE, GFW, MCP, VPS recovery, service restarts, BMC issues), and provides self-healing workflows. Contains six sub-skills — install the main skill to activate them all.

[![astra-sre](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-sre)](https://github.com/alrcatraz/astra-sre)

### 🔌 astra-knowledge-base-mcp

A Model Context Protocol (MCP) server that provides persistent vector-based knowledge storage. Key-value storage with semantic search — used by astra-sre for incident records, by the ecosystem for dynamic reference data, and as a general memory layer for any Hermes workflow.

[![astra-knowledge-base-mcp](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-knowledge-base-mcp)](https://github.com/alrcatraz/astra-knowledge-base-mcp)

### 🖥️ astra-camofox-browser

A headless browser automation service (fork of Camoufox) with persistent profiles and remote API control. Used for anti-detection browsing, session management, and automated web interactions.

[![astra-camofox-browser](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=astra-camofox-browser)](https://github.com/alrcatraz/astra-camofox-browser)

### 📘 Hermes Agent Tutorial

A three-volume Chinese-language tutorial covering Hermes Agent from zero to advanced proficiency. Currently in planning.

[![hermes-agent-tutorial](https://github-readme-stats.vercel.app/api/pin/?username=alrcatraz&repo=hermes-agent-tutorial)](https://github.com/alrcatraz/hermes-agent-tutorial)

---

## 🧭 Directory Structure

```
astra-aiagent-infra/
├── registry.yaml            ← ☝️ Core entry: ecosystem overview
├── skills/                  ← Ecosystem skills bundled in this repo
│   ├── devops/
│   │   └── astra-hub/       ← Ecosystem map index (this document as a skill)
├── mcp/                     ← MCP design documents
├── templates/               ← Scaffolding templates for new components
├── docs/                    ← Cross-component design standards & guides
├── lifecycle/               ← Lifecycle hook syncing tools
├── .gitignore
└── LICENSE
```

---

## License

MIT © 2026 [alrcatraz](https://github.com/alrcatraz)

<div align="center">

<img src="https://api.star-history.com/chart?repos=alrcatraz/astra-aiagent-infra,alrcatraz/astra-skill-execution-framework,alrcatraz/astra-skill-change-safeguard,alrcatraz/astra-skill-deploy-register,alrcatraz/astra-skill-pre-action-research,alrcatraz/astra-skill-work-closure-check,alrcatraz/astra-sre,alrcatraz/astra-camofox-browser,alrcatraz/hermes-agent-tutorial,alrcatraz/astra-knowledge-base-mcp&type=date" width="600" alt="Star History Chart" />

</div>

---

## 中文版

### 这是什么

这不是一个传统意义上的"代码仓库"——它是一个**生态门户**。
每个组件都有独立的仓库、独立的版本管理和发布节奏。

本仓库同时也托管以下组件：
- **`skills/devops/astra-hub/`** — 生态地图索引技能
- **`lifecycle/astra-lifecycle-sync.py`** — 生命周期钩子同步工具

### 快速开始

核心工作流 skill（5 个）是生态的基础：

| Skill | 作用 |
|:------|:-----|
| **execution-framework** | 任务分类路由，引导执行正确的工作流 |
| **pre-action-research** | 确保执行前充分调研 |
| **change-safeguard** | 改前保全，改后验证 |
| **deploy-register** | 部署即登记，纳入健康检查体系 |
| **work-closure-check** | 任务收尾检查清单 |

需要监控能力时加上 **astra-sre** 和 **astra-knowledge-base-mcp**。

想知道全貌？加载本仓库中的 **astra-hub** skill 即可查看完整的生态地图。
