---
name: astra-sre
description: "Unified SRE coordinating layer for multi-node infrastructure — orchestrates health scanning, incident triage, guided repair, and a learning loop across all managed devices. Delegates domain-specific fix logic to sub-skills; never duplicates their work."
version: 1.0.0
author: alrcatraz
platforms: [linux]
metadata:
  hermes:
    tags: [sre, site-reliability, infrastructure, monitoring, incident-response, orchestration]
related_skills:
  - astra-hub
  - astra-sre-fix-e2ee
  - astra-sre-proxy-daemon
  - astra-sre-restart-service
  - astra-sre-fix-gfw
  - astra-sre-fix-mcp
  - astra-sre-fix-vps-recovery
  - server-restart-recovery
  - server-health-audit
  - infrastructure-device-inventory
  - service-inventory
  - crash-marker-pattern
  - full-e2ee-recovery-after-server-rebuild
  - pre-upgrade-server-backup
triggers:
  - astra-sre
  - unified
  - coordinating
  - layer
  - multi
  - node
  - infrastructure
  - orchestrates
  - health
  - scanning
---

# astra-sre — Unified Infrastructure Reliability

## Trigger Conditions

Load this skill when:
- Setting up or extending the SRE monitoring/recovery pipeline
- Designing the architecture for the coordinated infrastructure management layer
- Adding a new device or service to the monitoring scope
- Evaluating whether an incident warrants a new sub-skill or a patch to an existing one

## Architecture: Coordinating Layer Pattern

astra-sre is NOT a monolith. It is a **thin orchestrator** that sits above existing foundational skills and delegates specialised work to sub-skills.

```
astra-sre (orchestrator)
  │
  ├── Schedule & dispatch health checks
  ├── Triage severity + impact
  ├── Route known faults → existing sub-skill
  ├── Guide novel faults → diagnostics → learning
  └── Verify fix → update knowledge base
       │
       ▼ calls upon
  ┌──────────────┬──────────────┬────────────────┐
  │ server-      │  crash-      │  full-e2ee-    │
  │ restart-     │  marker-     │  recovery-     │
  │ recovery     │  pattern     │  after-...      │
  │ (skill)      │  (skill)     │  (skill)        │
  └──────────────┴──────────────┴────────────────┘
```

### Principles

1. **Each tool does one thing.** Sub-skills own domain-specific logic (E2EE fix, disk cleanup, synapse restart, etc.). astra-sre only owns coordination.

2. **Every repair step is user-confirmed.** Display the planned action → show expected impact → ask "proceed?" → execute → verify. Never auto-fix without consent. (SOUL.md #4: 先保全再改, #5: 递进验证)

3. **Detection before diagnosis before repair.** Always follow the dependency order: is the machine reachable? → is the OS healthy? → is the service running? → what's the root cause? Never jump straight to repair.

4. **Learn, don't repeat.** Every incident feeds back into the knowledge base. Same fault twice → skill creation triggers.

5. **方案 before 执行, even for non-repair changes.** After audit, compile findings into a structured方案 — what changed, what needs updating, why, impact, priority order. Present to user. Wait for explicit approval. Only then start modifying files. This applies to config updates, cross-reference patches, documentation edits, and SOUL.md changes — not just repairs. The gap between "knowing what's wrong" and "fixing it" is where方案 approval lives. (SOUL.md #1.1: 研究先行，方案求精)

## Phased Priority

### 🥇 Phase 1 — Unified Health Scan + Tiered Alerts
- Single **`health-scan.py`** script covers ALL known devices (reads `config/devices.yaml` — copy from `devices.yaml.example`)
- Scores each device P0–P3
- Results pushed to Matrix via daily briefing cron (cron ID: `e6d8318767aa`)
- **Read-only.** Zero risk to production.
- Action: `cd ~/.astra/repos/astra-sre && uv run python3 scripts/health-scan.py`
- Cron: `no_agent` mode (script stdout delivered verbatim — no LLM). Wrapper at `~/.hermes/scripts/astra-sre-scan.sh` uses `uv run` for clean Python dependency isolation — do NOT use system python or hardcoded venv paths.
- Deployment details: See `references/deployment.md` for cron config, Home room thread, device access matrix, Phase 1 checklist, and the no_agent conversion rationale.
- **Separate concern:** The hourly service-level health check (MCPs, APIs, DB) lives under the `service-inventory` skill — it's the complement to astra-sre's device-level scan, not part of it.

### 🥈 Phase 2 — Diagnostics + Knowledge Base
- `sre_incidents` KB populated with 2 example incident records (MCP memory leak, health check false positive) as universal references — personal incident records are kept live in the local SQLite KB but not committed to the repo
- `triage.py` CLI tool at `scripts/triage.py` — search sre_incidents for matching past incidents using SQLite FTS5
  ```bash
  cd ~/.astra/repos/astra-sre
  python3 scripts/triage.py "symptoms here"
  python3 scripts/triage.py --list
  ```
- Diagnosis uses `health-scan.py --json` for current system state combined with `triage.py` for historical context:
  ```bash
  cd ~/.astra/repos/astra-sre
  python3 scripts/triage.py "sync error"               # search for similar past incidents
  python3 scripts/health-scan.py --json                 # collect live system state
  ```
- Not found in KB → write full diagnosis + root cause
- Found → pull previous fix path as first candidate
- **Knowledge base is the first shot.** Don't escalate to skill creation yet.

### 🥉 Phase 3 — Guided Repair (Design v1.0)

- astra-sre proposes a repair plan based on diagnosis
- **Three-tier operation level** (by impact, not by action):
  - **L1** (fully auto): no service impact — config changes, cache clear, notification replay
  - **L2** (auto + notify): brief/optional service impact — restart non-critical services, run read-only diagnostics
  - **L3** (human gate): irreversible or high-risk — data deletion, token change, service rebuild
- **Every automatic fix step must have a verify probe** — reuse `health-scan.py --mode <probe>` to compare before/after state. If state worsened → trigger rollback or escalate.
- **Lock mechanism with stale-PID detection** — lock files at `/tmp/astra-sre-lock-<tag>.lock` contain PID + timestamp. On acquire: if old PID is dead → auto-clear (handles SIGKILL / crash residuals). `kill -0 <PID>` for liveness check (sends no signal). No hard timeout — repair may take hours (e.g. `zypper dup`).
- **Single repair per problem class at a time** — lock by incident tag prevents watchdog and diagnose from stepping on each other.
- Full design: `~/Projects/astra/astra-sre/references/phase3-design.md`
- **Existing skill integration needed**: `full-e2ee-recovery-after-server-rebuild` and `astra-sre-fix-e2ee` need their steps classified L1/L2/L3 so auto-safe steps can run without user confirmation. See `references/phase3-design.md` for the classification table.

**Current sub-skills:** (5 total in `sre/` category)
| Sub-skill | Level | Status | Created |
|:----------|:-----:|:-------|:-------:|
| astra-sre-fix-e2ee | L2/L3 | ✅ Classified | Manual |
| astra-sre-restart-service | L2/L3 | ✅ Built | Phase 3 |
| astra-sre-fix-gfw | L2 | ✅ Auto-generated | learn.py |
| astra-sre-fix-mcp | L2 | ✅ Auto-generated | learn.py |
| astra-sre-fix-vps-recovery | L2/L3 | ✅ Auto-generated (references existing skills) | learn.py |

### 🏅 Phase 4 — Learning Loop ✅ COMPLETE

- **`learn.py`** at `scripts/learn.py` — "两次原则" scanner that checks sre_incidents for problem patterns with 2+ occurrences and no corresponding sub-skill. Groups by canonicalised tags (e2ee, gfw, healthcheck, vps-recovery, credential, resource-cleanup). Generates SKILL.md templates for missing skills.
  ```bash
  python3 scripts/learn.py                 # full report
  python3 scripts/learn.py --cron          # silent unless new
  python3 scripts/learn.py --suggest       # templates only
  ```
- Auto-generated 3 sub-skills: `astra-sre-fix-gfw`, `astra-sre-fix-mcp`, `astra-sre-fix-vps-recovery`
- Cron: monthly 1st via `astra-sre-refresh.sh` (no_agent, silent unless changes) — refreshes references + runs learn.py --cron
- **Same fault appears a second time** → create or patch a sub-skill
- **After each incident** → write formatted post-mortem report to KB structure (symptom → diagnosis → root cause → fix → commands)
- **Periodically audit** sub-skill library for stale/consolidatable entries

## Sub-Skill Delegation Model

When astra-sre detects a fault, it follows this decision tree:

```
Fault detected
  │
  ├─ Known fault type → delegate to sub-skill
  │   (e.g. "E2EE desync" → astra-sre-fix-e2ee)
  │
  └─ Novel/unknown → Phase 2 diagnostics path
      │
      ├─ Manual fix + KB write (first occurrence)
      │
      └─ Same fault again → create sub-skill or patch
```

**Sub-skill naming convention:** `astra-sre-fix-<domain>` — placed under `~/.hermes/skills/sre/` category.

**Each sub-skill must include:**
- Exact trigger conditions
- Step-by-step fix procedure (user-confirmed per step)
- Verification command
- Rollback plan if fix fails

## Two-Strike Rule (Skill Creation vs Patch)

A solved incident is handled differently depending on recurrence:

| Occurrence | Action | Rationale |
|:-----------|:-------|:----------|
| **1st time** | Manual fix → root cause written to KB MCP. Done. | Most problems are one-offs. Don't waste effort automating noise. |
| **2nd time** | Decide: patch existing sub-skill OR create new one? → See decision tree below. | Two data points confirm a pattern worth codifying. |
| **3+ times** | Track frequency in KB. If density is high, consider a prevention skill (not just fix). | Pattern is structural — need to prevent, not just react. |

### Patch vs Create Decision Tree

```
Same fault, second occurrence
  │
  ├─ Belongs to an existing sub-skill's domain?
  │   ├─ Yes → Patch that sub-skill (add case, extend trigger)
  │   └─ No  → Continue
  │
  ├─ Existing sub-skill already too broad/unwieldy?
  │   ├─ Yes → Create new sub-skill, split cleanly
  │   └─ No  → Patch existing
  │
  └─ Nature of the fix:
      ├─ Procedural variant of known fix → Patch
      └─ Entirely new service/failure mode → Create
```

## Existing Skills That astra-sre Orchestrates

| Skill | Role in SRE Pipeline |
|:------|:---------------------|
| `astra-hub` | Master index: project map, credential guide, cron overview, KB routing |
| `infrastructure-device-inventory` | Which machines exist, how to reach them (EasyTier/ZT/TS) — **SRE asset layer** |
| `service-inventory` | Which services run on each machine, health check endpoints — **SRE data layer** |
| `server-health-audit` | Periodic full audit (disk, mem, proc, net, cron, leaks) |
| `crash-marker-pattern` | Offline crash notification via marker files |
| `server-restart-recovery` | Full post-restart recovery playbook (pre-flight + post-verification) |
| `full-e2ee-recovery-after-server-rebuild` | Specialised E2EE Gateway recovery |
| `pre-upgrade-server-backup` | Layered backup before any destructive operation |

## Knowledge Base Spaces

| Space | Content | When to query | Status |
|:------|:--------|:--------------|:------|
| `sre_incidents` 🆕 | Incident records: root cause, diagnosis, fix steps, lessons | After every incident | **2 example entries** (universal patterns) + live local DB |
| `dynamic_ref` 🆕 | Mutable reference data: gateway length limits, format conventions, preference-query-map | Monthly cron refresh | **4 entries** |
| `hermes_config` | Hermes config: external services/MCPs/CLIs/ports | Deploy time | Active |
| `service_mgmt` | Service management: health checks, maintenance logs | Runtime | Active |

## Tools

### learn.py — "两次原则" Pattern Detector

A CLI tool in `scripts/learn.py` that scans `sre_incidents` for problem patterns with 2+ occurrences, checks if a corresponding sub-skill exists, and suggests creating one if missing.

```bash
cd ~/.astra/repos/astra-sre
python3 scripts/learn.py                 # full report
python3 scripts/learn.py --cron          # silent unless new suggestion
python3 scripts/learn.py --suggest       # show only suggestions
```

Groups incidents by canonicalised tags (e2ee, gfw, healthcheck, vps-recovery, credential, resource-cleanup). Generates a SKILL.md template for any pattern missing a sub-skill. Cron mode (`--cron`) exits silently when nothing to report.

### triage.py — Incident Knowledge Base Search

A CLI tool at `scripts/triage.py` that searches `sre_incidents` using SQLite FTS5:

```bash
cd ~/.astra/repos/astra-sre
python3 scripts/triage.py "symptoms here"     # Search for matching incidents
python3 scripts/triage.py --list              # List all recorded incidents
```

Combined with `health-scan.py --json` for current system state during diagnosis.

### health-scan.py — Multi-Device Health Probe

A CLI tool at `scripts/health-scan.py` that SSH-es into all configured devices and collects:

- **System** — disk %, memory, load, uptime, top processes
- **Services** — systemd service status configuration per device
- **Network** — basic reachability

```bash
cd ~/.astra/repos/astra-sre
python3 scripts/health-scan.py                # Markdown report
python3 scripts/health-scan.py --json         # Machine-readable
```

Reads `config/devices.yaml` (configured by copying from `devices.yaml.example`).

## SOUL.md Alignment

As SRE implementation patterns solidify, the relevant SOUL.md work principles should be updated to reflect lessons learned — keeping the principles **generic** (not referencing astra-* specifics) so they serve as a universal foundation.

This session established:
- **4.2 部署即登记** — From "Markdown/DB/kb 均可" (vague) to explicit criteria (maintainable, auto-checkable, clean deprecation). No implementation details leaked.
- **2.4 回环地址隔离** — New principle distilled from infrastructure practice. The **principle** (use 127.0.0.x per service) is in SOUL.md; the **specific allocation** (which x for what) stays in Fact Store as a preference.
- **5.1 查询顺序脱敏** — Replaced `astra-hub skill` with `本地参考索引` to keep SOUL.md generic for tutorial reuse (3-volume plan). SOUL.md no longer references implementation-specific names.
- **流程性规则强制执行模式** — 4 new enforceability skills created: pre-action-research, change-safeguard, deploy-register, work-closure-check. SOUL.md describes principles; skill descriptions use trigger keywords so Hermes' auto-scan mechanism forces procedural compliance.
- **凭证四分存储** — Credential files split into personal/work/other/temporary groups, each GPG-encrypted. Passphrase stored in .env as `GPG_Key_Alrcatraz` for headless access.
- **YAML 凭证 schema** — Standardized device credential structure with hostname, OS, network (interfaces+overlay), connection paths (priority-ordered with multi-hop), roles, access methods, accounts with is_admin flags, and nested service accounts.

Check SOUL.md for staleness whenever:
- A new core infrastructure pattern stabilises across multiple deployments
- A skill's implementation reveals a general lesson that other sessions could benefit from
- A vague SOUL.md description now has a concrete implementation behind it

## Pitfalls

1. **Resist scope creep.** astra-sre's job is coordinating, not implementing. If you find yourself writing domain-specific fix logic inside astra-sre, that logic belongs in a sub-skill.

2. **Knowledge base is not a dump.** Write structured entries: symptom → diagnosis → root cause → fix applied → commands used. Unstructured notes are noise.

3. **Two-strike rule is a guardrail, not a straitjacket.** If a first-occurrence fault is clearly part of a repeatable pattern (e.g. "disk full on /tmp" which happens monthly), feel empowered to create the sub-skill on the first strike. The rule prevents waste from one-offs, not prevents good judgement.

4. **Phase 1 is read-only.** Until Phase 3, astra-sre never writes to production systems. This is a deliberate safety boundary. Respect it.

5. **Auto-fix is gated by impact, not all-or-nothing.** L1 (no service impact) runs fully auto. L2 (brief impact) auto + notifies you. L3 (irreversible) requires your approval. This avoids both extremes — never auto-fixing anything (slow) and auto-fixing everything (dangerous). See `references/phase3-design.md` for the full classification.

6. **Credentials go in GPG, not in skill text.** When a fix step needs a password (e.g. SSH fallback), use `gpg --batch --no-tty --passphrase-fd 0 --pinentry-mode loopback --decrypt ~/Documents/credentials/personal-credentials.yaml.gpg 2>/dev/null` via stdin pipe — never hardcode in skill text. Credentials are grouped into four files by category (personal/work/other/temporary). See `astra-hub` skill for the full credential access guide.

7. **Knowledge base is searchable — use it.** Before diagnosing a novel fault, always `kb_search("sre_incidents", <symptom>)` first. Many problems have been seen before.

8. **Lock files survive crashes.** If a repair process is SIGKILL'd or the host crashes, `/tmp/astra-sre-lock-*.lock` files persist. The lock mechanism handles this via PID liveness check (`kill -0`). If a fix or diagnostic script finds a lock file, check `cat /tmp/astra-sre-lock-*.lock` for the PID — if `kill -0 <PID>` returns non-zero, the lock is stale; delete it and proceed. Do NOT hardcode lock-bypass logic.

9. **Post-completion systemic audit — don't stop after the main fix.** After any significant system change, follow this 9-point scan to catch ripple effects (implements SOUL.md §3.1 同类扫描 + §1.1 方案求精):

   | # | Check | What to look for |
   |:--|:------|:-----------------|
   | ① | **Ecosystem skills scan** | Do related skills need `related_skills` updates? Any stale cross-references? |
   | ② | **Cron job drift** | Between cron list and documented intent — any mismatch? |
   | ③ | **Fact Store completeness** | Add durable facts about the new system state |
   | ④ | **SOUL.md alignment** | Does any principle need updating? Audit ALL principles, not just the one you think is relevant. |
   | ⑤ | **Memory accuracy** | Does memory still reflect current reality? Stale paths? |
   | ⑥ | **Backlink verification** | Who references what you changed? Load each and check the link is live. |
   | ⑦ | **File existence verification** | Search by glob, not by path assumption. Default-path searches miss non-default categories. |
   | ⑧ | **Content duplication** | Scan for repeated blocks; merge or remove. |
   | ⑨ **方案 → 批准 → 执行** | After audit, compile findings into a方案. Present to user. Wait for approval. **Then** touch files. Skipping this gate means you're working without consent. |

## Reference Documents

| Path | Content |
|:-----|:--------|
| `references/phase3-design.md` | Full Phase 3 design: L1/L2/L3 levels, lock mechanism, existing skill integration plan (British English) |
| `references/ecosystem-survey.md` | Survey of which services map to which devices and sub-skills |
| `references/deployment.md` | Cron config, Home room thread IDs, Phase 1 checklist |
