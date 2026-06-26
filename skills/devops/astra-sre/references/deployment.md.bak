# astra-sre Deployment Reference

> Last updated: 2026-06-18
> Relates to: Phase 1 (Unified Health Scan) on-disk artifacts

## Phase 1 Artifacts

```
~/Projects/astra/astra-sre/
├── config/
│   └── devices.yaml           ← 8 devices: vps-hk, vps-uk, ds425plus,
│                                 suset01, homecentre01, susetlearn00,
│                                 openwrt, star (fedoratg removed)
├── scripts/
│   ├── health-scan.py         ← Primary: Python, supports markdown/JSON
│   └── health-scan.sh         ← Fallback: Shell, Bash-only alternative
└── references/
    └── format-convention.md   ← Project-wide format rules
```

### Run Commands

```bash
# Standard (default markdown output)
cd ~/.astra/repos/astra-sre && python3 scripts/health-scan.py

# Brief-only (summary without full device details)
cd ~/.astra/repos/astra-sre && python3 scripts/health-scan.py --brief

# JSON output for programmatic consumption
cd ~/.astra/repos/astra-sre && python3 scripts/health-scan.py --output json
```

> **Note on Python runtime:** When running via cron, always use `uv run` (uv's own venv management), not system python and not a hardcoded Hermes venv path. This keeps dependency isolation clean. The repo doesn't need a pyproject.toml — `uv run` auto-resolves installed packages via its cache. See the Cron Job section below for the actual wrapper pattern.

## Cron Job Configuration

### Daily Briefing — astra-sre 每日巡检

| Field | Value |
|:------|:------|
| Job ID | `e6d8318767aa` |
| Name | `astra-sre 每日巡检` |
| Schedule | `0 8 * * *` (daily 08:00 HKT) |
| Mode | `no_agent` (script stdout delivered verbatim — no LLM middleman) |
| Script | `astra-sre-scan.sh` (wrapper in `~/.hermes/scripts/`) |
| Workdir | `~/.astra/repos/astra-sre` |
| Deliver | Home room thread: `$yet-ZxogvPVJ49kNzefDe3PXuSIikcOrTlcYx8oGIi4` |
| Status | ✅ Running, daily reports in Home room 📊 thread |

**Wrapper script** (`~/.hermes/scripts/astra-sre-scan.sh`):

```bash
#!/bin/bash
set -euo pipefail
REPO_DIR="$HOME/.astra/repos/astra-sre"
cd "$REPO_DIR"
unset VIRTUAL_ENV          # don't leak Hermes venv into uv
exec uv run python3 scripts/health-scan.py
```

### Historical: LLM-Driven Mode → no_agent Conversion

**When:** 2026-06-18

**Why:** The original cron job was LLM-driven (agent → `terminal()` → script → pipe → LLM response → deliver). Starting 2026-06-16, every run failed with `RuntimeError: [Errno 32] Broken pipe`. Root cause: the agent's stdout pipe closed during the long script execution (90+ seconds scanning 8 devices via SSH), while the LLM was still waiting for tool output.

**Fix:** Converted to `no_agent=true` — the script runs as a standalone subprocess; its stdout is delivered verbatim. No LLM overhead, no pipe breakage, no token waste.

**Rules of thumb for cron job mode selection:**

| Task type | Mode | Rationale |
|:----------|:----:|:----------|
| Run script → deliver stdout verbatim | `no_agent` | Pure mechanical task. LLM adds nothing but risk (Broken pipe, latency, token cost). |
| Summarize data, decide what to report, or reason about output | `agent` (LLM-driven) | Needs LLM judgement. Use long timeouts and keep output small. |

### Related Cron Jobs (Separate System)

| Job | Owner | Mode | Relation |
|:----|:------|:----:|:---------|
| `服务健康检查` (`30a6bc5ad07e`) | `service-inventory` | `no_agent` | Service-level (MCP, API, DB) — different scope from device-level |
| E2EE watchdog/health | `service-inventory` refs | `no_agent` | Gateway-level — separate concern |

## Home Room Thread Structure

The 📊 prefix thread (`$yet-...`) in Home room groups all infrastructure monitoring:

```
Home Room — 📊 服务健康/设备监控
├─ [$yet-...] astra-sre 每日巡检          ← daily 08:00, no_agent
├─ [$wOVg-...] 服务健康检查                ← hourly, no_agent (silent when healthy)
└─ (other monitoring threads with 🛡️ prefix for E2EE)
```

## Device Access Matrix

| Device | SSH Alias | Key | Status |
|:-------|:----------|:----|:-------|
| vps-hk | `root@10.20.4.10:2222` | `id_ed25519` | ✅ |
| vps-uk | `root@10.10.4.11` | `id_ed25519` | ✅ |
| ds425plus | `Alrcatraz@10.20.3.10` | `id_ed25519` | ✅ |
| suset01 | `alrcatraz@10.20.2.14` | `id_ed25519` | ✅ (mobile, may be offline) |
| homecentre01 | `localhost` | `id_ed25519` | ✅ (this machine) |
| susetlearn00 | `alrcatraz@192.168.0.20` | `id_ed25519` | ✅ (LAN, often offline in this room) |
| openwrt | `root@192.168.0.1:22` | `id_ed25519` | ⚠️ (no key, password access) |
| star | `star@172.18.177.195:22` | `id_ed25519` | ✅ (GPU server via jump host) |

## Phase 1 Deployment Checklist

- [x] `config/devices.yaml` — 8 devices registered with SSH targets, keys, thresholds
- [x] `scripts/health-scan.py` — Python scanning engine with markdown/JSON output
- [x] `scripts/health-scan.sh` — Shell fallback (Bash)
- [x] Cron job deployed (daily 08:00, `no_agent` mode via shell wrapper + `uv run`)
- [x] Home room thread created with initial message
- [x] Device scan verified working for SSH-key-configured machines
- [ ] SSH key deployment for `openwrt` (key: `pending` in config)
- [ ] `uv run` .venv checked into repo or pyproject.toml for explicit deps

## Lessons Learned

### 1. Mechanical cron tasks → `no_agent`

If a cron job's prompt is "run script X and deliver its output verbatim", it should be `no_agent=true` from day one. The LLM-driven path adds:
- Token cost (agent startup + tool processing + response generation)
- Latency (~30s agent warmup)
- Failure surface (Broken pipe when the LLM's stdout pipe closes during long script execution)

### 2. Cron script Python runtime → `uv run`

When a cron wrapper script needs to run a Python utility:
- ❌ **System python** — may lack deps (pyyaml not installed, PEP 668 lock)
- ❌ **Direct Hermes venv path** (`~/.hermes/hermes-agent/venv/bin/python3`) — too coupled to agent internals
- ✅ **`uv run`** — uv manages its own venv, auto-resolves installed packages, clean isolation

Always `unset VIRTUAL_ENV` before `uv run` in a wrapper script to prevent Hermes' venv from leaking into uv's project detection.
