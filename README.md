# Astra AI Agent Infrastructure (astra-aiagent-infra)

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

| Category | Component | Repository | Status |
|:---------|:----------|:-----------|:------:|
| 📘 Tutorial | Hermes Agent Tutorial (3 vols) | `alrcatraz/hermes-agent-tutorial` | 🟡 Planning |
| 🔧 Skill | pre-action-research | `alrcatraz/astra-skill-pre-action-research` | 🟢 Active |
| 🔧 Skill | change-safeguard | `alrcatraz/astra-skill-change-safeguard` | 🟢 Active |
| 🔧 Skill | deploy-register | `alrcatraz/astra-skill-deploy-register` | 🟢 Active |
| 🔧 Skill | work-closure-check | `alrcatraz/astra-skill-work-closure-check` | 🟢 Active |
| 🛡️ SRE | astra-sre coordination layer | `alrcatraz/astra-sre` | 🟢 Active |
| 🔌 MCP | astra-knowledge-base | `alrcatraz/astra-knowledge-base-mcp` | 🟢 Active |

> Full details (descriptions, transport types, etc.) → [`registry.yaml`](registry.yaml)

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

## 🤝 License

MIT © 2026 Nanaly
