---
name: astra-hub
description: "astar-* ecosystem map index: memory/knowledge routing, project index, credential security guide, quick reference"
version: 1.1.0
category: devops
platforms: [linux]
---

# astra-hub — Ecosystem Map Index

> Load this skill to get the full navigation overview of the astra-* ecosystem.
> Companion to SOUL.md §5.1. Does not store actual credential values.

---

## 🗺️ Memory & Knowledge Routing

| Query target | Primary location | Fallback | Notes |
|:-------------|:-----------------|:---------|:------|
| User preferences summary | `fact_store probe user_pref` (by tag) | — | Update dynamic_ref "preference-query-map" when adding new preference categories |
| Full reference documentation | `kb_search("dynamic_ref", <keyword>)` | — | Monthly cron checks for updates |
| Incident records | `kb_search("sre_incidents", <keyword>)` | This skill's stored experience | Write in after every incident |
| Service configuration | `kb_search("hermes_config", <keyword>)` | — | Register on deploy |
| Service status | `kb_search("service_mgmt", <keyword>)` | — | Updated by cron health checks |
| Project index | **This skill** (see next section) | — | Update when adding new astra-* projects |

---

## 🏗️ Public / Private Workspace Architecture

> If you wish to contribute to projects in this ecosystem, consider
> isolating working directories from the directories your agent uses:
> - `~/Projects/astra/<repo>` for public code (pushed to GitHub),
> - `~/.astra/repos/<repo>` for private working copies (with personal data overlays).

### Directory Responsibilities

| Path | Content | Sync Strategy |
|:-----|:--------|:--------------|
| `~/Projects/astra/<repo>/` | Public code (sanitised, no personal data), remote → GitHub | Push / pull from GitHub |
| `~/.astra/repos/<repo>/` | Private copy (git clone from GitHub + personal data overlays) | `git pull` from GitHub syncs code framework |
| `~/.astra/config/` | Personal configuration files | `.gitignored`, not committed |
| `~/.astra/scripts/` | Personal admin scripts | `.gitignored`, not committed |

### Workflow

```
Push code changes to GitHub (from public copy):
  cd ~/Projects/astra/<repo> && git push

Pull code updates from GitHub (into private copy):
  cd ~/.astra/repos/<repo> && git pull
  Personal data files are in .gitignore, unaffected

Add personal data to private copy:
  Place config files in ~/.astra/repos/<repo>/config/
  Add to .gitignore (confirm it exists first)
```

## 📦 astra-* Project Index

| Project | GitHub | Public Path | Purpose | Key Files |
|:--------|:------:|:------------|:--------|:----------|
| **astra-sre** | ✅ | ~/Projects/astra/astra-sre/ | SRE coordination layer | scripts/health-scan.py |
| **astra-knowledge-base-mcp** | ✅ | ~/Projects/astra/astra-knowledge-base-mcp/ | Knowledge base MCP service | server.py |
| **astra-camofox-browser** | ✅ fork | ~/Projects/astra/astra-camofox-browser/ | Browser automation (fork) | server.js |
| **astra-aiagent-infra** | ✅ | ~/Projects/astra/astra-aiagent-infra/ | Portal meta-repo + lifecycle hooks | registry.yaml, lifecycle/astra-lifecycle-sync.py |
| **astra-aiagent-infra-template** | ✅ | — | Template repository | — |
| **astra-vcs-assist** | ✅ | ~/Projects/astra/astra-vcs-assist/ | VCS workflow orchestration (GPG key, Git init/dev/release/sync) | SKILL.md, routing.yaml, gpg/astra-vcs-assist-gpg-key/, git/skills/ |
| **astra-skill-execution-framework** | ✅ | ~/Projects/astra/astra-skill-execution-framework/ | Task classification router | SKILL.md, scripts/sync-routing.py |
| **astra-skill-change-safeguard** | ✅ | ~/Projects/astra/astra-skill-change-safeguard/ | Modification safety checklists | SKILL.md |
| **astra-skill-deploy-register** | ✅ | ~/Projects/astra/astra-skill-deploy-register/ | Deployment registration checklists | SKILL.md |
| **astra-skill-pre-action-research** | ✅ | ~/Projects/astra/astra-skill-pre-action-research/ | Pre-action research | SKILL.md |
| **astra-skill-work-closure-check** | ✅ | ~/Projects/astra/astra-skill-work-closure-check/ | Task closure checklist | SKILL.md |

## 🔐 Credential Security Guide (Example)

> Principle: never store actual credential values in skills. Credentials should be
> managed in separate files by category, all properly encrypted.
> The following shows a recommended grouping and examples.

### Recommended Groups

| Group | Example Scope |
|:------|:--------------|
| **🔵 Personal** | Own devices (servers, workstations, NAS, VPS) |
| **🟠 Work** | Client / work servers and devices |
| **🟢 Other** | Friends, family, shared devices |
| **⚪ Temporary** | One-time access, discard after use |

**Usage:**
- Personal / Work / Other → decrypt encrypted file, look up by tag
- Temporary → provided on the spot, discarded after use

### Secure Access Examples

| Credential type | Recommended storage | Retrieval method | Notes |
|:----------------|:-------------------|:-----------------|:------|
| API tokens | `.env` file | Read natively by framework, not via terminal | ✅ Safe |
| SSH private keys | `~/.ssh/id_*` | Automatically used by SSH | ✅ Deploy to all devices |
| Device passwords | Grouped encrypted files | Decrypt file, grep by key | Managed per group |
| Recovery keys | `.env` file | Read natively by framework | ✅ Safe |

### Known Redaction Risk Operations

- `sudo -S` piping → ❌ Blocked; use framework's built-in credential injection
- `echo | sshpass -p 'xxx'` → ⚠️ High risk; prefer SSH keys
- Passing passwords in terminal arguments → ⚠️ May trigger log/output redaction
- GPG decryption via stdin → ✅ Safe (password never appears in args or output)

### Credentials in Memory — Principles

- Device passwords → reference to encrypted file
- SSH key paths → allowed (not credential values)
- Usernames / domains / ports → allowed
- Passwords / tokens / private key content → ❌ **Forbidden**
- Sudo password → reference to encrypted file

> Full setup procedure: see `references/gpg-credential-setup.md`.

---

## Quick Reference (Example Structure)

### Automated Maintenance Tasks (Example)

| Cron task | Frequency | Type | Description |
|:----------|:---------:|:----:|:------------|
| **KeePass sync** | Periodic | no_agent script | Merge NAS Sync library into local master |
| **Full device scan** | Daily | agent | Unified health scan |
| **SRE knowledge base refresh** | Monthly | no_agent script | Refresh KB + scan for updates |
| **Skill staleness check** | Monthly | no_agent script | Check skills for outdated content |

### Background Services

| Service | Type | Port | Description |
|:--------|:----:|:----:|:------------|
| **Path Optimizer** | cron | — | Multi-path selection (tunnel-optional) |

### Patch Management (Example Structure)

| Patch name | Location | Purpose |
|:-----------|:---------|:--------|
| example-patch | `~/.hermes/patches/` | Describe manual patches and recovery methods |

### Key Script Locations (Example)

| Script | Purpose | Notes |
|:-------|:--------|:------|
| `scripts/watchdog.sh` | Real-time daemon | Used with fault-recovery skills |
| `scripts/health.sh` | Health check | Periodic execution |
| `scripts/repair.py` | Automated repair | Called by watchdog |
| `scripts/refresh.sh` | Offline fallback | Used when pypi is unreachable |

### SSH Alias Examples

| Alias | Target | Identity file |
|:------|:-------|:--------------|
| `ssh my-server` | user@<server-ip-or-host> | ~/.ssh/id_ed25519 |
| `ssh my-nas` | user@<nas-hostname> | ~/.ssh/id_ed25519 |

### Knowledge Base Spaces

| Space | Purpose |
|:------|:--------|
| hermes_config | Hermes config: external services / MCP / CLI / ports |
| service_mgmt | Management plans: health checks / maintenance logs |
| sre_incidents | Incident records: root cause analysis / repair experience |
| dynamic_ref | Dynamic reference data: platform limits / formatting conventions |

### Path Quick Reference (Example)

| Path | Content |
|:-----|:--------|
| `~/Projects/astra/<repo>/` | Public astra-* projects (push to GitHub) |
| `~/.astra/repos/<repo>/` | Private working copies (personal data overlays) |
| `~/.astra/config/` | Personal configuration files |
| `~/.astra/scripts/` | Personal admin scripts |
