# User-Local Storage Configuration

> Local instance of the information storage hierarchy.
> General decision tree → see `astra-hub` SKILL.md § 信息存储层级.
> This file contains your specific store names, paths, and conventions.

---

## Knowledge Base Spaces

| Space | Purpose | Maintained by |
|:------|:--------|:--------------|
| `hermes_config` | Service/MCP/CLI config (name, port, path, healthcheck) | On deploy |
| `service_mgmt` | Management plans: health check config, maintenance logs | On operations |
| `sre_incidents` | Incident records: root cause analysis, repair experience | After incidents |
| `dynamic_ref` | Volatile reference data: Gateway message limits, format conventions | Monthly cron |

## Credential Stores

| Store | Path | Type |
|:------|:-----|:-----|
| Personal devices | `~/Documents/credentials/personal-credentials.yaml.gpg` | GPG-encrypted YAML |
| Work devices | `~/Documents/credentials/work-credentials.yaml.gpg` | GPG-encrypted YAML |
| Other devices | `~/Documents/credentials/other-credentials.yaml.gpg` | GPG-encrypted YAML |
| Bootstrap secrets | `~/.hermes/.env` | `.env` file |
| Service accounts | KeePassXC database | Local DB |

See `credential-store-management` skill for the full three-layer protocol.

## Project Paths

| Path | Content |
|:-----|:--------|
| `~/Projects/astra/` | Public astra-* repos (push to GitHub) |
| `~/.astra/repos/` | Private working copies (personal data overlays) |
| `~/.astra/config/` | Personal config (devices.yaml, format-convention.md) |
| `~/.astra/scripts/` | Personal scripts (diagnose.py, etc.) |
| `~/Projects/linux/` | Linux system tools (dnf-pri, rime-copr, nvidia-cuda-setup-*) |
| `~/.hermes/skills/` | Hermes skill deployment directory |
| `~/Documents/credentials/` | Credential index + GPG encrypted files |
| `~/Extra/DS425Plus/` | NAS mounted extra data |

## Persistent Memory (MEMORY.md) Conventions

- **Fact Store** (`category=user_pref`): user preferences, communication style, toolchain choices
- **MEMORY.md**: stable environment facts (IPs, paths, versions, project structures)
- Do NOT store: task progress, session outputs, PR numbers, commit SHAs, temporary TODO items
- Do NOT store: any plaintext credentials (use `→GPG creds` references only)

## Illustration: Decision Tree Applied to Your Setup

From the general decision tree in SKILL.md, here are concrete examples
of correct vs incorrect storage in your environment:

| Scenario | Correct destination | Common misplacement | Why |
|:---------|:-------------------|:--------------------|:----|
| "智谱用 zai provider" | **MEMORY.md** | Fact Store | Stable env fact, not preference |
| "zypper 优先于 Homebrew" | **Fact Store (user_pref)** | MEMORY.md | Is a preference, not env fact |
| "SearXNG 在 127.0.0.2:8931" | **hermes_config KB** | Fact Store / MEMORY.md | Config info, should be auto-syncable |
| "Gateway 消息长度上限" | **dynamic_ref KB** | MEMORY.md | Volatile reference data |
| "部署新 MCP → 写 hermes_config" | **Skill (deploy-register)** | — | Procedural knowledge |
| "E2EE OTK 修复步骤" | **sre_incidents KB** | Fact Store | Incident record with root cause |
| "@hermes00 token invalidated" | **sre_incidents KB** | Fact Store (was deleted) | Incident record, not persistent fact |
| "用户喜欢 British English" | **Fact Store (user_pref)** | — | Clear communication preference |
