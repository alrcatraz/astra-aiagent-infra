# Ecosystem Survey: SRE-Related Tools from awesome-hermes-agent

Survey date: 2026-06-07
Source: [0xNyk/awesome-hermes-agent](https://github.com/0xNyk/awesome-hermes-agent) (3.8k ★)

## rtk-hermes (Token Compression Plugin)

**Repo:** [ogallotti/rtk-hermes](https://github.com/ogallotti/rtk-hermes)
**Parent:** [rtk-ai/rtk](https://github.com/rtk-ai/rtk) (59.5k ★)

### What it does
Hermes plugin that intercepts terminal commands via `pre_tool_call` hook, rewrites them through `rtk rewrite` before execution. Filtered output reaches the LLM instead of raw command output. Claims 60-90% token reduction.

### Assessment: NOT RECOMMENDED for our setup

| Factor | Verdict |
|:-------|:--------|
| Target audience | AI coding agents (Claude Code, Codex, Cursor) — not infrastructure SRE |
| Commands it optimises | git, cargo, npm, pytest, ls, cat — NOT systemctl, journalctl, zypper, ssh |
| Our workload | 80% SSH backend commands — RTK requires `rtk` binary on every remote host |
| Our token bottleneck | Matrix messages + Gateway interactions, not terminal output |
| Information loss risk | Output filtering = lossy compression. Could strip critical context from diagnostic commands |
| Deployment cost | RTK binary on every machine + plugin config + backend whitelist + debugging layer |

**Verdict:** Great for coding agents, negligible benefit for our infra-focused workflow. Revisit if we start doing significant local code development.

---

## hermes-incident-commander (Autonomous SRE Skill)

**Repo:** [Lethe044/hermes-incident-commander](https://github.com/Lethe044/hermes-incident-commander)

### What it does
Hermes skill that runs cron-based health checks (every 5 min), detects incidents, classifies severity (P0-P3), runs parallel diagnostics via sub-agents, applies tiered fixes, verifies resolution, writes post-incident reports, and auto-creates prevention SKILL.md files.

### Assessment: ARCHITECTURAL INSPIRATION, NOT FOR DIRECT USE

| Factor | Verdict |
|:-------|:--------|
| Closed-loop automation | Conceptually sound — detect → diagnose → fix → verify → learn |
| Auto-fix without user consent | ❌ Incompatible with our safety principles (SOUL.md #4: 每步皆有交代) |
| Auto-skill-creation | ✅ Valuable — adapted in astra-sre's "two-strike rule" |
| Multi-service parallel diagnosis | ✅ Valuable — sub-agent dispatch model worth adopting |
| Production readiness | Beta — challenge submission project, not battle-tested |
| Alert delivery | Telegram/Discord only — we use Matrix |

**What we took from it:**
- The detect → diagnose → fix → verify → learn pipeline structure
- Sub-agent parallel dispatch for multi-service incidents
- Auto-skill-creation on recurring faults (adapted as two-strike rule)

**What we rejected:**
- Unattended auto-fix (user confirmation required at every step)
- Black-box LLM decisions about what to run on production servers

---

## Other Ecosystem Items of Interest

### For future reference

| Project | What | When to Revisit |
|:--------|:-----|:-----------------|
| `SkillClaw` | Auto-evolve/deduplicate skill library from session data | If skill library grows past ~50 entries |
| `hermes-hub` | Community skill registry | If we want to publish astra-sre |
| `agenttrace` | CLI session audit TUI (token/tool/failure heatmaps) | If debugging complex multi-agent flows |
| `lintlang` | Static linter for agent configs | If config.yaml grows complex enough to need validation |
